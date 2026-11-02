"""TikTok LIVE source: reads a LIVE anonymously with the TikTokLive library.

This module has two parts:

1. **Event mapping** — small functions that turn TikTokLive events into our
   ``RelayEvent``. They only read attributes, so tests can pass simple fake
   objects instead of real TikTokLive events.
2. **TikTokSource** — connects, waits while the user is not live, reconnects
   after problems, and reports its status (added below).

Facts about TikTokLive 7.0.1 used here are listed in CLAUDE.md §8.
"""

import asyncio
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx
from TikTokLive import TikTokLiveClient
from TikTokLive.client.errors import (
    AgeRestrictedError,
    SignatureRateLimitError,
    TikTokLiveError,
    UserNotFoundError,
    UserOfflineError,
    WebcastBlockedError,
)
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    GiftEvent,
    LikeEvent,
    LiveEndEvent,
    SocialEvent,
)

from streambridge.core.events import ConnectionStatus, RelayEvent
from streambridge.sources.base import EmitEvent, ReportStatus, Source

logger = logging.getLogger(__name__)

PLATFORM = "tiktok"

# Wait between "is the user live yet?" checks (safe for the Euler free tier).
OFFLINE_RECHECK_SECONDS = 90.0
# Waits before reconnecting after an error or a lost connection; the last repeats.
RECONNECT_BACKOFF_SECONDS: tuple[float, ...] = (5.0, 10.0, 30.0, 60.0)
# Longest time to wait for the connection to close cleanly.
CLOSE_TIMEOUT_SECONDS = 5.0
MAX_NAME_LENGTH = 50
FALLBACK_VIEWER_NAME = "TikTok viewer"

_WHITESPACE = re.compile(r"\s+")
# Zero-width joiner glues emoji together (👨‍👩‍👧); keep it.
_KEEP_FORMAT_CHARS = {"‍"}


# --- small helpers ---------------------------------------------------------


def clean_username(value: str) -> str:
    """Turn ``@name``, ``name`` or a TikTok URL into the bare username."""
    text = value.strip()
    text = re.sub(r"^https?://(www\.)?tiktok\.com/", "", text, flags=re.IGNORECASE)
    text = text.removesuffix("/live").strip("/")
    return text.removeprefix("@").strip()


def clean_name(name: str | None, fallback: str = FALLBACK_VIEWER_NAME) -> str:
    """Make a viewer name safe to show: no invisible characters, single spaces, max 50 chars."""
    if not name:
        return fallback
    visible = "".join(
        char
        for char in name
        if char in _KEEP_FORMAT_CHARS or unicodedata.category(char) not in ("Cc", "Cf")
    )
    text = _WHITESPACE.sub(" ", visible).strip()
    if not text:
        return fallback
    if len(text) > MAX_NAME_LENGTH:
        text = text[: MAX_NAME_LENGTH - 1].rstrip() + "…"
    return text


def display_key(event: Any) -> str:
    """Return the lower-case ``common.display_text.key`` of an event, or ``""``."""
    common = getattr(event, "common", None)
    display_text = getattr(common, "display_text", None)
    key = getattr(display_text, "key", "") or ""
    return str(key).lower()


def viewer_of(event: Any) -> tuple[str, str]:
    """Return ``(display name, @handle)`` of the viewer behind an event."""
    user = getattr(event, "user", None)
    handle = str(getattr(user, "unique_id", "") or "")
    name = clean_name(getattr(user, "nickname", None), fallback=handle or FALLBACK_VIEWER_NAME)
    return name, handle


def _relay_event(kind: str, event: Any, **values: Any) -> RelayEvent:
    """Build a RelayEvent with the viewer filled in."""
    name, handle = viewer_of(event)
    return RelayEvent(kind=kind, platform=PLATFORM, user=name, user_id=handle, **values)


# --- event mapping -----------------------------------------------------------


def map_comment(event: Any) -> RelayEvent | None:
    """``CommentEvent`` -> ``chat`` (empty comments are ignored)."""
    text = str(getattr(event, "content", "") or "").strip()
    if not text:
        return None
    return _relay_event("chat", event, text=text)


def map_gift(event: Any) -> RelayEvent | None:
    """``GiftEvent`` -> ``gift``, but only when a streak has ended.

    While a viewer is still tapping a streakable gift, TikTok sends one event
    per tap with ``streaking=True``; the final event has the full count.
    """
    if getattr(event, "streaking", False):
        return None
    gift = getattr(event, "gift", None)
    gift_name = str(getattr(gift, "name", "") or "").strip()
    if not gift_name:
        return None
    count = int(getattr(event, "repeat_count", 1) or 1)
    return _relay_event("gift", event, gift_name=gift_name, gift_count=max(1, count))


def map_like(event: Any) -> RelayEvent:
    """``LikeEvent`` -> ``like`` (only the first like per viewer is relayed later)."""
    return _relay_event("like", event)


def social_kind(event: Any) -> str | None:
    """Classify a ``SocialEvent`` as ``follow``, ``repost`` or ``share`` (or ``None``).

    TikTokLive itself only knows follow and share, by looking for those words in
    ``common.display_text.key``. A repost goes through TikTok's share menu; if
    its key turns out to contain "repost" it is recognised here, otherwise it
    is reported as a share. The raw data is logged so we can find out.
    """
    key = display_key(event)
    if "follow" in key:
        return "follow"
    if "repost" in key:
        return "repost"
    if "share" in key:
        return "share"
    return None


def map_social(event: Any) -> RelayEvent | None:
    """``SocialEvent`` -> ``follow`` / ``share`` / ``repost`` (unknown kinds are ignored)."""
    kind = social_kind(event)
    if kind is None:
        return None
    return _relay_event(kind, event)


def social_raw_data(event: Any) -> dict[str, Any]:
    """The raw fields of a SocialEvent that may tell a repost from a share."""
    _, handle = viewer_of(event)
    return {
        "key": display_key(event),
        "share_type": getattr(event, "share_type", None),
        "action": getattr(event, "action", None),
        "share_target": getattr(event, "share_target", None),
        "scene": getattr(event, "scene", None),
        "user": handle,
    }


# --- the source ----------------------------------------------------------------

ClientFactory = Callable[[str, str | None], Any]
Sleep = Callable[[float], Awaitable[None]]
RawListener = Callable[[dict[str, Any]], None]


def create_client(username: str, euler_key: str | None) -> TikTokLiveClient:
    """Create a fresh TikTokLive client, with the user's Euler API key if given."""
    web_kwargs = {"signer_kwargs": {"sign_api_key": euler_key}} if euler_key else None
    return TikTokLiveClient(unique_id=username, web_kwargs=web_kwargs)


class Outcome(Enum):
    """How one connection attempt ended."""

    OFFLINE = "offline"  # the user is not live
    LIVE_ENDED = "live_ended"  # we were connected and the LIVE ended
    LOST = "lost"  # the connection dropped or failed for a temporary reason
    ERROR = "error"  # TikTok refused (blocked, rate limited, not found, ...)


@dataclass
class Attempt:
    """Result of one connection attempt.

    Attributes:
        outcome: How it ended.
        detail: Short explanation for the UI and logs.
        was_connected: True if the LIVE was reached before it ended.
    """

    outcome: Outcome
    detail: str = ""
    was_connected: bool = False


def describe_error(error: BaseException) -> Attempt:
    """Turn an exception from a connection attempt into an Attempt."""
    if isinstance(error, UserOfflineError):
        return Attempt(Outcome.OFFLINE)
    if isinstance(error, UserNotFoundError):
        return Attempt(Outcome.ERROR, "account not found, or it has no LIVE access")
    if isinstance(error, SignatureRateLimitError):
        return Attempt(Outcome.ERROR, "sign server rate limit reached (add an Euler API key)")
    if isinstance(error, WebcastBlockedError):
        return Attempt(Outcome.ERROR, "TikTok blocked the connection")
    if isinstance(error, AgeRestrictedError):
        return Attempt(Outcome.ERROR, "this LIVE is age-restricted")
    if isinstance(error, TikTokLiveError):
        return Attempt(Outcome.ERROR, str(error))
    if isinstance(error, httpx.HTTPError | OSError):
        return Attempt(Outcome.LOST, f"network problem: {error}")
    return Attempt(Outcome.ERROR, f"unexpected error: {error}")


class TikTokSource(Source):
    """Reads one TikTok LIVE and keeps trying until it is stopped.

    Status flow::

        connecting -> connected -> (LIVE ends) -> waiting_live -> connecting ...
        connecting -> (not live) -> waiting_live, re-check every 90 s
        connecting -> (error / lost) -> disconnected or error, retry after 5/10/30/60 s
    """

    name = "tiktok"

    def __init__(
        self,
        username: str,
        euler_key: str | None = None,
        client_factory: ClientFactory = create_client,
        sleep: Sleep = asyncio.sleep,
        raw_listener: RawListener | None = None,
    ) -> None:
        """Create the source.

        Args:
            username: TikTok username of the LIVE (with or without ``@``).
            euler_key: Optional Euler Stream API key (higher rate limits).
            client_factory: Creates a TikTokLive client (replaceable in tests).
            sleep: Waits a number of seconds (replaceable in tests).
            raw_listener: Called with raw follow/share data (for finding reposts).
        """
        self.username = clean_username(username)
        self._euler_key = euler_key or None
        self._client_factory = client_factory
        self._sleep = sleep
        self._raw_listener = raw_listener
        self._failures = 0

    async def run(self, emit: EmitEvent, report_status: ReportStatus) -> None:
        """Connect, wait and reconnect forever (until the task is cancelled)."""
        handle = f"@{self.username}"
        while True:
            report_status(ConnectionStatus.CONNECTING, handle)
            attempt = await self._connect_once(emit, report_status)
            if attempt.was_connected:
                self._failures = 0

            if attempt.outcome in (Outcome.OFFLINE, Outcome.LIVE_ENDED):
                self._failures = 0
                wait = OFFLINE_RECHECK_SECONDS
                report_status(
                    ConnectionStatus.WAITING_LIVE,
                    f"{handle} is not live; checking again in {wait:.0f} s",
                )
            else:
                wait = self._next_backoff()
                status = (
                    ConnectionStatus.ERROR
                    if attempt.outcome == Outcome.ERROR
                    else ConnectionStatus.DISCONNECTED
                )
                report_status(status, f"{attempt.detail}; retrying in {wait:.0f} s")
            logger.info("TikTok %s: %s (%s)", handle, attempt.outcome.value, attempt.detail)
            await self._sleep(wait)

    def _next_backoff(self) -> float:
        """Return the next reconnect wait and remember one more failure."""
        index = min(self._failures, len(RECONNECT_BACKOFF_SECONDS) - 1)
        self._failures += 1
        return RECONNECT_BACKOFF_SECONDS[index]

    async def _connect_once(self, emit: EmitEvent, report_status: ReportStatus) -> Attempt:
        """Make one connection, relay events until it ends, and say how it ended."""
        client = self._client_factory(self.username, self._euler_key)
        state = _AttemptState()
        self._add_handlers(client, emit, report_status, state)
        try:
            connection = await client.start(fetch_live_check=True)
            await connection
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not isinstance(error, UserOfflineError):
                logger.warning("TikTok connection failed: %r", error)
            attempt = describe_error(error)
            attempt.was_connected = state.connected
            return attempt
        finally:
            await self._close(client)

        if state.live_ended:
            return Attempt(Outcome.LIVE_ENDED, "the LIVE ended", was_connected=True)
        return Attempt(Outcome.LOST, "connection lost", was_connected=state.connected)

    def _add_handlers(
        self, client: Any, emit: EmitEvent, report_status: ReportStatus, state: "_AttemptState"
    ) -> None:
        """Register event handlers on a fresh client."""

        def on_connect(_event: Any) -> None:
            state.connected = True
            self._failures = 0
            report_status(ConnectionStatus.CONNECTED, f"@{self.username}")

        def on_live_end(_event: Any) -> None:
            state.live_ended = True

        def on_social(event: Any) -> None:
            raw = social_raw_data(event)
            logger.info("TikTok social event raw data: %s", raw)
            if self._raw_listener is not None:
                self._raw_listener(raw)
            _emit_mapped(emit, map_social(event))

        handlers: dict[type, Callable[[Any], None]] = {
            ConnectEvent: on_connect,
            LiveEndEvent: on_live_end,
            CommentEvent: lambda event: _emit_mapped(emit, map_comment(event)),
            GiftEvent: lambda event: _emit_mapped(emit, map_gift(event)),
            LikeEvent: lambda event: _emit_mapped(emit, map_like(event)),
            SocialEvent: on_social,
        }
        for event_type, handler in handlers.items():
            client.on(event_type, _safe(handler))

    @staticmethod
    async def _close(client: Any) -> None:
        """Close the connection and the HTTP session; never raise."""
        steps = (client.disconnect, client.web.close)
        for step in steps:
            try:
                await asyncio.wait_for(step(), timeout=CLOSE_TIMEOUT_SECONDS)
            except (Exception, asyncio.CancelledError) as error:
                # Cancellation of the outer task is re-raised after this cleanup.
                logger.debug("Ignoring error while closing TikTok client: %r", error)


@dataclass
class _AttemptState:
    """What happened during one connection attempt."""

    connected: bool = False
    live_ended: bool = False


def _emit_mapped(emit: EmitEvent, event: RelayEvent | None) -> None:
    """Pass a mapped event on, unless mapping produced nothing."""
    if event is not None:
        emit(event)


def _safe(handler: Callable[[Any], None]) -> Callable[[Any], None]:
    """Wrap a handler so one bad event can never break the TikTok connection."""

    def wrapper(event: Any) -> None:
        try:
            handler(event)
        except Exception:
            logger.exception("Error while handling a TikTok event")

    return wrapper
