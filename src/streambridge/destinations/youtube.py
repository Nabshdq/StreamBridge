"""YouTube live chat destination.

Sends messages with ``liveChatMessages.insert``. The Google client library is
synchronous, so every call runs in a worker thread (``asyncio.to_thread``) and
the engine's event loop never blocks.

Finding the live chat (checked against the YouTube docs, 2026-11-04):

- Channel owner (default): ``liveBroadcasts.list(mine=true)`` and pick the
  broadcast that is ``live``. ``mine`` must be the only filter. Its
  ``snippet.liveChatId`` is the chat to write to. Cost: 1 quota unit.
- Bot account: the user pastes the live URL; ``videos.list`` with
  ``liveStreamingDetails`` gives ``activeLiveChatId``. Cost: 1 quota unit.

When there is no live yet, the chat id is looked up again at most once every
``LOOKUP_INTERVAL`` seconds (each look-up costs quota), and sending is retried
by the engine in between.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from streambridge.auth.google_oauth import YouTubeAuthError, load_credentials
from streambridge.core.formatter import YOUTUBE_MAX_LENGTH
from streambridge.core.outqueue import YOUTUBE_MAX_QUEUE
from streambridge.core.quota import (
    COST_BROADCASTS_LIST,
    COST_INSERT,
    COST_VIDEOS_LIST,
    QuotaTracker,
)
from streambridge.core.ratelimit import YOUTUBE_RULES
from streambridge.core.secrets import SecretStore
from streambridge.destinations.base import Destination, SendResult, TemporarySendError

logger = logging.getLogger(__name__)

LOOKUP_INTERVAL = 60.0

REASON_QUOTA = "YouTube daily quota is used up; sending resumes after midnight Pacific Time"
REASON_LOGIN = "YouTube login expired; please log in again"
REASON_NO_LIVE = "YouTube live chat not found yet (waiting for the live to start)"
REASON_FORBIDDEN = "YouTube does not allow this account to chat here"

_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}
_RETRY_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "backendError"}
_CHAT_GONE_REASONS = {"liveChatEnded", "liveChatNotFound", "liveChatDisabled"}

ServiceFactory = Callable[[], Any]
Clock = Callable[[], float]


def video_id_from_url(url: str) -> str | None:
    """Extract the video id from a YouTube watch, live, shorts or youtu.be link."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return parsed.path.strip("/") or None
    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2 and parts[0] in ("live", "shorts", "embed"):
            return parts[1]
    return None


def error_reason(error: HttpError) -> str:
    """Return Google's short error reason (like ``quotaExceeded``), or an empty text."""
    try:
        body = json.loads(error.content.decode("utf-8"))
        return str(body["error"]["errors"][0]["reason"])
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return ""


class YouTubeDestination(Destination):
    """Sends relayed messages to a YouTube live chat."""

    name = "youtube"
    max_length = YOUTUBE_MAX_LENGTH
    rate_rules = YOUTUBE_RULES
    max_queue_size = YOUTUBE_MAX_QUEUE

    def __init__(
        self,
        store: SecretStore,
        quota: QuotaTracker,
        live_url: str = "",
        service_factory: ServiceFactory | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        """Create the destination (nothing is contacted until ``start``).

        Args:
            store: Where the Google login is kept.
            quota: Local daily quota counter; every API call is recorded in it.
            live_url: A live URL to use instead of looking up the user's own
                broadcast (needed for a separate bot account).
            service_factory: Builds the Google client. Tests pass a fake.
            clock: Monotonic seconds, for the look-up pause.
        """
        self.quota = quota
        self._store = store
        self._live_url = live_url
        self._service_factory = service_factory or self._build_service
        self._clock = clock
        self._service: Any = None
        self._chat_id: str | None = None
        self._last_lookup: float | None = None

    @property
    def waiting_for_live(self) -> bool:
        """True while no live chat has been found yet (shown as a status)."""
        return self._chat_id is None

    async def start(self) -> None:
        """Sign in with the saved login and prepare the Google client."""
        self._service = await asyncio.to_thread(self._service_factory)

    async def stop(self) -> None:
        """Forget the client (the library keeps no open connections for us)."""
        self._service = None

    async def send(self, text: str) -> SendResult:
        """Send one message to the live chat.

        Raises:
            TemporarySendError: when there is no live yet, or Google asks us
                to slow down or is briefly unavailable.
        """
        if self._service is None:
            await self.start()
        if self.quota.remaining < COST_INSERT:
            return SendResult(ok=False, reason=REASON_QUOTA)
        if self._chat_id is None:
            await self._find_chat_id()
        try:
            await asyncio.to_thread(self._insert, self._chat_id, text)
        except HttpError as error:
            return self._handle_http_error(error)
        except OSError as error:  # network down, timeouts, DNS
            raise TemporarySendError(str(error)) from error
        finally:
            self.quota.record(COST_INSERT)
        return SendResult(ok=True)

    # --- finding the chat -------------------------------------------------

    async def _find_chat_id(self) -> None:
        """Look up the live chat id, at most once per ``LOOKUP_INTERVAL``."""
        now = self._clock()
        if self._last_lookup is not None and now - self._last_lookup < LOOKUP_INTERVAL:
            raise TemporarySendError(REASON_NO_LIVE)
        self._last_lookup = now
        try:
            chat_id = await asyncio.to_thread(self._lookup_chat_id)
        except HttpError as error:
            result = self._handle_http_error(error)
            raise TemporarySendError(result.reason) from error
        except OSError as error:
            raise TemporarySendError(str(error)) from error
        if chat_id is None:
            raise TemporarySendError(REASON_NO_LIVE)
        self._chat_id = chat_id
        logger.info("YouTube live chat found")

    def _lookup_chat_id(self) -> str | None:
        """Blocking look-up of the live chat id (runs in a worker thread)."""
        if self._live_url:
            return self._chat_id_from_video(self._live_url)
        return self._chat_id_from_own_broadcast()

    def _chat_id_from_video(self, url: str) -> str | None:
        video_id = video_id_from_url(url)
        if video_id is None:
            logger.warning("The YouTube live URL has no video id")
            return None
        self.quota.record(COST_VIDEOS_LIST)
        response = self._service.videos().list(part="liveStreamingDetails", id=video_id).execute()
        for item in response.get("items", []):
            chat_id = item.get("liveStreamingDetails", {}).get("activeLiveChatId")
            if chat_id:
                return str(chat_id)
        return None

    def _chat_id_from_own_broadcast(self) -> str | None:
        self.quota.record(COST_BROADCASTS_LIST)
        # ``mine`` has to be the only filter, so the live one is picked here.
        response = self._service.liveBroadcasts().list(part="snippet,status", mine=True).execute()
        for item in response.get("items", []):
            if item.get("status", {}).get("lifeCycleStatus") == "live":
                chat_id = item.get("snippet", {}).get("liveChatId")
                if chat_id:
                    return str(chat_id)
        return None

    # --- sending ----------------------------------------------------------

    def _insert(self, chat_id: str | None, text: str) -> None:
        """Blocking ``liveChatMessages.insert`` (runs in a worker thread)."""
        body = {
            "snippet": {
                "liveChatId": chat_id,
                "type": "textMessageEvent",
                "textMessageDetails": {"messageText": text},
            }
        }
        self._service.liveChatMessages().insert(part="snippet", body=body).execute()

    def _handle_http_error(self, error: HttpError) -> SendResult:
        """Turn a Google error into a refusal or a retry."""
        status = error.resp.status
        reason = error_reason(error)
        logger.warning("YouTube error %s (%s)", status, reason or "no reason")
        if reason in _QUOTA_REASONS:
            return SendResult(ok=False, reason=REASON_QUOTA)
        if reason in _CHAT_GONE_REASONS:
            self._chat_id = None  # the live ended; look for the next one
            raise TemporarySendError(REASON_NO_LIVE) from error
        if status == 401:
            return SendResult(ok=False, reason=REASON_LOGIN)
        if status == 403:
            if reason in _RETRY_REASONS:
                raise TemporarySendError(reason) from error
            return SendResult(ok=False, reason=REASON_FORBIDDEN)
        if status == 429 or status >= 500 or reason in _RETRY_REASONS:
            raise TemporarySendError(reason or f"HTTP {status}") from error
        return SendResult(ok=False, reason=reason or f"HTTP {status}")

    def _build_service(self) -> Any:
        """Build the real Google client from the saved login (worker thread)."""
        credentials = load_credentials(self._store)
        if credentials is None:
            raise YouTubeAuthError("Not logged in to YouTube yet.")
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)
