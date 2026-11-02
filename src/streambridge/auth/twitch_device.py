"""Twitch login with the Device Code Flow (no client secret needed).

How a login works:

1. ``start_device_flow`` asks Twitch for a short code, e.g. ``ABCDEFGH``.
2. The user opens ``verification_uri`` (twitch.tv/activate, code pre-filled)
   and clicks Authorize.
3. ``wait_for_authorization`` polls Twitch until the user has approved and
   returns the tokens.

Afterwards ``TwitchAccount`` keeps the tokens valid: it validates them (Twitch
requires this on start and every hour) and refreshes them when needed. Tokens
are stored in the Windows Credential Manager (``core.secrets``).

Details of the Twitch endpoints are listed in CLAUDE.md §8 (verified 2026-11-02).
"""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from streambridge.core.secrets import SecretStore, load_json, save_json

logger = logging.getLogger(__name__)

# StreamBridge's public Twitch app. Client IDs are not secret.
# TODO(owner): fill in once the Twitch app "StreamBridge" is registered (public client).
TWITCH_CLIENT_ID = ""
CLIENT_ID_ENV = "STREAMBRIDGE_TWITCH_CLIENT_ID"

DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

SCOPE_WRITE_CHAT = "user:write:chat"
SCOPE_READ_MODERATED = "user:read:moderated_channels"
BROADCASTER_SCOPES: tuple[str, ...] = (SCOPE_WRITE_CHAT,)
BOT_SCOPES: tuple[str, ...] = (SCOPE_WRITE_CHAT, SCOPE_READ_MODERATED)

HTTP_TIMEOUT_SECONDS = 15.0
SLOW_DOWN_EXTRA_SECONDS = 5.0

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class TwitchSetupError(Exception):
    """StreamBridge itself is not set up for Twitch (for example no client ID)."""


class TwitchAuthError(Exception):
    """The user has to log in to Twitch (again)."""


def get_client_id() -> str:
    """Return the Twitch client ID, or raise if it has not been filled in yet."""
    client_id = os.environ.get(CLIENT_ID_ENV, "").strip() or TWITCH_CLIENT_ID
    if not client_id:
        raise TwitchSetupError(
            "The StreamBridge Twitch app is not registered yet (no client ID). "
            f"Set {CLIENT_ID_ENV} for development."
        )
    return client_id


@dataclass(frozen=True)
class DeviceCode:
    """The code the user must approve on twitch.tv/activate."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: float
    interval: float


@dataclass(frozen=True)
class TokenInfo:
    """What ``/oauth2/validate`` says about an access token."""

    user_id: str
    login: str
    scopes: tuple[str, ...]
    expires_in: float


@dataclass(frozen=True)
class TwitchTokens:
    """Tokens for one Twitch login."""

    access_token: str
    refresh_token: str
    scopes: tuple[str, ...] = ()
    user_id: str = ""
    login: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict (for the secret store)."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "scopes": list(self.scopes),
            "user_id": self.user_id,
            "login": self.login,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TwitchTokens | None":
        """Build tokens from a stored dict, or ``None`` if required parts are missing."""
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        if not isinstance(access, str) or not isinstance(refresh, str) or not access:
            return None
        scopes = data.get("scopes")
        return cls(
            access_token=access,
            refresh_token=refresh,
            scopes=tuple(s for s in scopes if isinstance(s, str))
            if isinstance(scopes, list)
            else (),
            user_id=str(data.get("user_id") or ""),
            login=str(data.get("login") or ""),
        )


def _error_message(response: httpx.Response) -> str:
    """Twitch puts error text in the JSON ``message`` field."""
    try:
        data = response.json()
    except ValueError:
        return response.text.strip()
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or "")
    return ""


def _tokens_from_response(data: dict[str, Any]) -> TwitchTokens:
    """Build tokens from a ``/oauth2/token`` success response."""
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    if not isinstance(access, str) or not isinstance(refresh, str):
        raise TwitchAuthError("Twitch returned an incomplete token response")
    scopes = data.get("scope") or []
    return TwitchTokens(
        access_token=access,
        refresh_token=refresh,
        scopes=tuple(scopes) if isinstance(scopes, list) else (),
    )


class TwitchAuth:
    """Talks to Twitch's OAuth endpoints."""

    def __init__(
        self,
        client_id: str,
        http: httpx.AsyncClient,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        """Create the helper.

        Args:
            client_id: StreamBridge's Twitch client ID.
            http: HTTP client to use (tests pass one with a fake transport).
            sleep: Waits a number of seconds (replaceable in tests).
            clock: Returns the current time in seconds (replaceable in tests).
        """
        self.client_id = client_id
        self._http = http
        self._sleep = sleep
        self._clock = clock

    async def start_device_flow(self, scopes: Sequence[str]) -> DeviceCode:
        """Ask Twitch for a code the user can approve."""
        response = await self._http.post(
            DEVICE_URL,
            data={"client_id": self.client_id, "scopes": " ".join(scopes)},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise TwitchAuthError(f"Could not start Twitch login: {_error_message(response)}")
        data = response.json()
        return DeviceCode(
            device_code=str(data["device_code"]),
            user_code=str(data["user_code"]),
            verification_uri=str(data["verification_uri"]),
            expires_in=float(data.get("expires_in", 1800)),
            interval=float(data.get("interval", 5)),
        )

    async def wait_for_authorization(
        self, device: DeviceCode, scopes: Sequence[str]
    ) -> TwitchTokens:
        """Poll Twitch until the user approves; return tokens with user id and login."""
        deadline = self._clock() + device.expires_in
        interval = device.interval
        while self._clock() < deadline:
            await self._sleep(interval)
            response = await self._http.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "scopes": " ".join(scopes),
                    "device_code": device.device_code,
                    "grant_type": DEVICE_GRANT_TYPE,
                },
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if response.status_code == 200:
                return await self._with_identity(_tokens_from_response(response.json()))
            message = _error_message(response)
            if message == "authorization_pending":
                continue
            if message == "slow_down":
                interval += SLOW_DOWN_EXTRA_SECONDS
                continue
            raise TwitchAuthError(f"Twitch login failed: {message or response.status_code}")
        raise TwitchAuthError("The Twitch login code expired. Please start the login again.")

    async def refresh(self, tokens: TwitchTokens) -> TwitchTokens:
        """Get new tokens with the refresh token (no secret needed for public apps)."""
        response = await self._http.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token,
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code in (400, 401):
            raise TwitchAuthError("The Twitch login has expired. Please log in again.")
        response.raise_for_status()
        fresh = _tokens_from_response(response.json())
        return TwitchTokens(
            access_token=fresh.access_token,
            refresh_token=fresh.refresh_token,
            scopes=fresh.scopes or tokens.scopes,
            user_id=tokens.user_id,
            login=tokens.login,
        )

    async def validate(self, access_token: str) -> TokenInfo | None:
        """Ask Twitch whether a token is still valid. ``None`` means it is not."""
        response = await self._http.get(
            VALIDATE_URL,
            headers={"Authorization": f"OAuth {access_token}"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code == 401:
            return None
        response.raise_for_status()
        data = response.json()
        return TokenInfo(
            user_id=str(data.get("user_id") or ""),
            login=str(data.get("login") or ""),
            scopes=tuple(data.get("scopes") or ()),
            expires_in=float(data.get("expires_in") or 0),
        )

    async def _with_identity(self, tokens: TwitchTokens) -> TwitchTokens:
        """Fill in the user id and login of new tokens."""
        info = await self.validate(tokens.access_token)
        if info is None:
            raise TwitchAuthError("Twitch rejected the new login token")
        return TwitchTokens(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            scopes=info.scopes or tokens.scopes,
            user_id=info.user_id,
            login=info.login,
        )


@dataclass
class TwitchAccount:
    """One Twitch login (the streamer or a bot) that keeps its tokens valid and saved.

    Attributes:
        auth: The OAuth helper.
        store: Where the tokens are saved.
        key: The secret key, e.g. ``twitch.broadcaster`` or ``twitch.bot``.
    """

    auth: TwitchAuth
    store: SecretStore
    key: str
    _tokens: TwitchTokens | None = field(default=None, init=False, repr=False)

    @property
    def tokens(self) -> TwitchTokens:
        """The current tokens. Raises if the account is not ready."""
        if self._tokens is None:
            raise TwitchAuthError("Not logged in to Twitch")
        return self._tokens

    def load(self) -> TwitchTokens | None:
        """Read saved tokens (without contacting Twitch)."""
        data = load_json(self.store, self.key)
        self._tokens = TwitchTokens.from_dict(data) if data else None
        return self._tokens

    async def login(
        self, scopes: Sequence[str], show_code: Callable[[DeviceCode], None]
    ) -> TwitchTokens:
        """Run the full device login, call ``show_code`` with the code, save the tokens."""
        device = await self.auth.start_device_flow(scopes)
        show_code(device)
        tokens = await self.auth.wait_for_authorization(device, scopes)
        self._save(tokens)
        return tokens

    async def ensure_valid(self) -> TwitchTokens:
        """Validate the saved tokens, refreshing them if needed. Raises if login is needed."""
        tokens = self._tokens or self.load()
        if tokens is None:
            raise TwitchAuthError("Not logged in to Twitch. Please log in first.")
        info = await self.auth.validate(tokens.access_token)
        if info is None:
            return await self.refresh()
        if info.user_id != tokens.user_id or info.login != tokens.login:
            tokens = TwitchTokens(
                tokens.access_token, tokens.refresh_token, info.scopes, info.user_id, info.login
            )
            self._save(tokens)
        self._tokens = tokens
        return tokens

    async def refresh(self) -> TwitchTokens:
        """Refresh the tokens and save the new ones (Twitch refresh tokens are single-use)."""
        fresh = await self.auth.refresh(self.tokens)
        self._save(fresh)
        return fresh

    def logout(self) -> None:
        """Forget the saved tokens."""
        self.store.delete(self.key)
        self._tokens = None

    def _save(self, tokens: TwitchTokens) -> None:
        """Remember and store tokens."""
        self._tokens = tokens
        save_json(self.store, self.key, tokens.to_dict())
