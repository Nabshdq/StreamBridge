"""Twitch chat destination (Helix ``POST /chat/messages``).

Two ways to send:

- **Streamer account** (default): the streamer logs in; messages appear as
  the streamer in their own chat.
- **Bot account** (advanced): a separate account logs in and posts to the
  streamer's channel. The bot **must be a moderator** there; this is checked
  on start, and Start fails with a clear message if it is not.

Behaviour when sending:

- Network problems, 429 (rate limit) and 5xx are temporary: the engine retries.
- 401 (token expired): refresh once and try again.
- ``is_sent=false`` (e.g. AutoMod), 403, 422: refused, reported, not retried.

The login is validated on start and every hour, as Twitch requires.
"""

import asyncio
import logging
from typing import Any

import httpx

from streambridge.auth.twitch_device import (
    HTTP_TIMEOUT_SECONDS,
    Sleep,
    TwitchAccount,
    TwitchAuth,
    TwitchAuthError,
    TwitchSetupError,
)
from streambridge.core.formatter import TWITCH_MAX_LENGTH
from streambridge.core.ratelimit import TWITCH_RULES
from streambridge.core.secrets import SecretStore
from streambridge.destinations.base import Destination, SendResult, TemporarySendError

logger = logging.getLogger(__name__)

HELIX_URL = "https://api.twitch.tv/helix"
VALIDATE_INTERVAL_SECONDS = 3600.0
MODERATED_PAGE_SIZE = 100

REASON_LOGIN_EXPIRED = "Twitch login expired; please log in again"
REASON_FORBIDDEN = (
    "Twitch does not allow this account to chat here (if you use a bot: is it still a moderator?)"
)
REASON_TOO_LONG = "message too long for Twitch"


class NotModeratorError(TwitchSetupError):
    """The bot account is not a moderator of the target channel."""


class TwitchDestination(Destination):
    """Sends relayed messages to a Twitch chat."""

    name = "twitch"
    max_length = TWITCH_MAX_LENGTH
    rate_rules = TWITCH_RULES
    max_queue_size = None  # Twitch: never drop messages

    def __init__(
        self,
        client_id: str,
        store: SecretStore,
        account_key: str,
        channel: str = "",
        bot_mode: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        validate_interval: float = VALIDATE_INTERVAL_SECONDS,
    ) -> None:
        """Create the destination (nothing is contacted until ``start``).

        Args:
            client_id: StreamBridge's Twitch client ID.
            store: Where the login tokens are kept.
            account_key: Which stored login to use (streamer or bot).
            channel: Target channel name (needed in bot mode).
            bot_mode: True when a separate bot account sends the messages.
            transport: HTTP transport override (tests use a fake Twitch).
            sleep: Waits a number of seconds (replaceable in tests).
            validate_interval: Seconds between login checks (Twitch requires hourly).
        """
        self._client_id = client_id
        self._store = store
        self._account_key = account_key
        self._channel = channel.strip().lstrip("@").lower()
        self._bot_mode = bot_mode
        self._transport = transport
        self._sleep = sleep
        self._validate_interval = validate_interval
        self._http: httpx.AsyncClient | None = None
        self._account: TwitchAccount | None = None
        self._broadcaster_id = ""
        self._sender_id = ""
        self._validator: asyncio.Task[None] | None = None

    @property
    def sender_login(self) -> str:
        """Login name of the account that sends (after ``start``)."""
        return self._account.tokens.login if self._account else ""

    async def start(self) -> None:
        """Check the login, find the channel, and (bot mode) check moderator status."""
        self._http = httpx.AsyncClient(transport=self._transport, timeout=HTTP_TIMEOUT_SECONDS)
        auth = TwitchAuth(self._client_id, self._http, sleep=self._sleep)
        self._account = TwitchAccount(auth, self._store, self._account_key)
        tokens = await self._account.ensure_valid()
        self._sender_id = tokens.user_id

        if self._bot_mode:
            if not self._channel:
                raise TwitchSetupError("Enter the Twitch channel the bot should post to.")
            self._broadcaster_id = await self._find_channel_id(self._channel)
            if not await self._is_moderator(self._broadcaster_id):
                raise NotModeratorError(
                    f"The bot @{tokens.login} is not a moderator of channel "
                    f"{self._channel}. Type /mod {tokens.login} in your Twitch chat, "
                    "then try again."
                )
        else:
            self._broadcaster_id = tokens.user_id

        self._validator = asyncio.create_task(self._validate_regularly())
        logger.info("Twitch ready: @%s -> channel id %s", tokens.login, self._broadcaster_id)

    async def send(self, text: str) -> SendResult:
        """Send one chat message."""
        try:
            response = await self._post_message(text)
            if response.status_code == 401:
                try:
                    await self._require_account().refresh()
                except TwitchAuthError:
                    return SendResult(ok=False, reason=REASON_LOGIN_EXPIRED)
                response = await self._post_message(text)
        except httpx.TransportError as error:
            raise TemporarySendError(f"network problem: {error}") from error
        return self._interpret(response)

    async def stop(self) -> None:
        """Stop the hourly check and close the HTTP connection."""
        if self._validator is not None:
            self._validator.cancel()
            await asyncio.gather(self._validator, return_exceptions=True)
            self._validator = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # --- helpers ---------------------------------------------------------------

    def _require_account(self) -> TwitchAccount:
        """The account, or an error if ``start`` was not called."""
        if self._account is None:
            raise TwitchSetupError("Twitch destination is not started")
        return self._account

    def _headers(self) -> dict[str, str]:
        """Headers for Helix requests."""
        return {
            "Authorization": f"Bearer {self._require_account().tokens.access_token}",
            "Client-Id": self._client_id,
        }

    async def _helix_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET a Helix endpoint and return the JSON body (raises on HTTP errors)."""
        assert self._http is not None
        response = await self._http.get(
            f"{HELIX_URL}{path}", params=params, headers=self._headers()
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    async def _find_channel_id(self, login: str) -> str:
        """Turn a channel name into its Twitch user id."""
        data = await self._helix_get("/users", {"login": login})
        users = data.get("data") or []
        if not users:
            raise TwitchSetupError(f"Twitch channel '{login}' was not found.")
        return str(users[0]["id"])

    async def _is_moderator(self, broadcaster_id: str) -> bool:
        """True if the logged-in account moderates ``broadcaster_id`` (all pages checked)."""
        params: dict[str, Any] = {"user_id": self._sender_id, "first": MODERATED_PAGE_SIZE}
        while True:
            data = await self._helix_get("/moderation/channels", params)
            channels = data.get("data") or []
            if any(str(c.get("broadcaster_id")) == broadcaster_id for c in channels):
                return True
            cursor = (data.get("pagination") or {}).get("cursor")
            if not cursor:
                return False
            params["after"] = cursor

    async def _post_message(self, text: str) -> httpx.Response:
        """POST one message to Helix."""
        assert self._http is not None
        return await self._http.post(
            f"{HELIX_URL}/chat/messages",
            json={
                "broadcaster_id": self._broadcaster_id,
                "sender_id": self._sender_id,
                "message": text,
            },
            headers=self._headers(),
        )

    @staticmethod
    def _interpret(response: httpx.Response) -> SendResult:
        """Turn a Helix response into a SendResult (or a retryable error)."""
        status = response.status_code
        if status == 429 or status >= 500:
            raise TemporarySendError(f"Twitch answered {status}")
        if status == 200:
            entries = (response.json() or {}).get("data") or [{}]
            entry = entries[0]
            if entry.get("is_sent", False):
                return SendResult(ok=True)
            drop = entry.get("drop_reason") or {}
            reason = drop.get("message") or drop.get("code") or "dropped by Twitch"
            return SendResult(ok=False, reason=str(reason))
        if status == 401:
            return SendResult(ok=False, reason=REASON_LOGIN_EXPIRED)
        if status == 403:
            return SendResult(ok=False, reason=REASON_FORBIDDEN)
        if status == 422:
            return SendResult(ok=False, reason=REASON_TOO_LONG)
        try:
            message = str((response.json() or {}).get("message") or "")
        except ValueError:
            message = ""
        return SendResult(ok=False, reason=message or f"Twitch answered {status}")

    async def _validate_regularly(self) -> None:
        """Check the login every hour (required by Twitch)."""
        while True:
            await self._sleep(self._validate_interval)
            await self.validate_once()

    async def validate_once(self) -> None:
        """Check the login now; log a clear error if it is no longer valid."""
        try:
            await self._require_account().ensure_valid()
        except TwitchAuthError as error:
            logger.error("Twitch login is no longer valid: %s", error)
        except httpx.HTTPError as error:
            logger.warning("Could not reach Twitch to check the login: %s", error)
