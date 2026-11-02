"""Tests for the Twitch device login (Twitch is simulated, no network)."""

from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest

from streambridge.auth import twitch_device
from streambridge.auth.twitch_device import (
    BOT_SCOPES,
    BROADCASTER_SCOPES,
    DEVICE_GRANT_TYPE,
    DeviceCode,
    TwitchAccount,
    TwitchAuth,
    TwitchAuthError,
    TwitchSetupError,
    TwitchTokens,
    get_client_id,
)
from streambridge.core.secrets import MemoryStore, load_json, save_json

CLIENT_ID = "test-client-id"
VALIDATE_OK = {
    "client_id": CLIENT_ID,
    "login": "nabil",
    "user_id": "1001",
    "scopes": ["user:write:chat"],
    "expires_in": 14000,
}

Handler = Callable[[httpx.Request], httpx.Response]


class FakeTime:
    """Clock and sleep that move together without real waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def form(request: httpx.Request) -> dict[str, str]:
    """Decode a form-encoded request body."""
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


def make_auth(handler: Handler, fake_time: FakeTime | None = None) -> TwitchAuth:
    """A TwitchAuth that talks to a fake Twitch."""
    fake_time = fake_time or FakeTime()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TwitchAuth(CLIENT_ID, http, sleep=fake_time.sleep, clock=fake_time.clock)


DEVICE = DeviceCode("dev-code", "ABCDEFGH", "https://www.twitch.tv/activate?x", 1800, 5)


# --- client id ---------------------------------------------------------------


def test_missing_client_id_explains(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a registered app, a clear setup error is raised."""
    monkeypatch.setattr(twitch_device, "TWITCH_CLIENT_ID", "")
    monkeypatch.delenv(twitch_device.CLIENT_ID_ENV, raising=False)
    with pytest.raises(TwitchSetupError):
        get_client_id()


def test_client_id_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Developers can set the client ID with an environment variable."""
    monkeypatch.setenv(twitch_device.CLIENT_ID_ENV, "from-env")
    assert get_client_id() == "from-env"


# --- device flow ---------------------------------------------------------------


async def test_start_device_flow_sends_client_and_scopes() -> None:
    """The device request carries the client ID and space-separated scopes."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(form(request))
        return httpx.Response(
            200,
            json={
                "device_code": "dev-code",
                "expires_in": 1800,
                "interval": 5,
                "user_code": "ABCDEFGH",
                "verification_uri": "https://www.twitch.tv/activate?public=true&device-code=ABCDEFGH",
            },
        )

    device = await make_auth(handler).start_device_flow(BOT_SCOPES)
    assert seen == {
        "client_id": CLIENT_ID,
        "scopes": "user:write:chat user:read:moderated_channels",
    }
    assert device.user_code == "ABCDEFGH"
    assert device.interval == 5


async def test_wait_until_user_approves() -> None:
    """Pending answers are retried every interval until tokens arrive."""
    answers = iter(["pending", "pending", "ok"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/validate"):
            return httpx.Response(200, json=VALIDATE_OK)
        assert form(request)["grant_type"] == DEVICE_GRANT_TYPE
        if next(answers) == "pending":
            return httpx.Response(400, json={"status": 400, "message": "authorization_pending"})
        return httpx.Response(
            200,
            json={
                "access_token": "acc",
                "refresh_token": "ref",
                "expires_in": 14000,
                "scope": ["user:write:chat"],
                "token_type": "bearer",
            },
        )

    fake_time = FakeTime()
    tokens = await make_auth(handler, fake_time).wait_for_authorization(DEVICE, BROADCASTER_SCOPES)
    assert tokens == TwitchTokens("acc", "ref", ("user:write:chat",), "1001", "nabil")
    assert fake_time.sleeps == [5, 5, 5]


async def test_slow_down_waits_longer() -> None:
    """A slow_down answer makes the polling interval longer."""
    answers = iter(["slow_down", "invalid device code"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"status": 400, "message": next(answers)})

    fake_time = FakeTime()
    with pytest.raises(TwitchAuthError):
        await make_auth(handler, fake_time).wait_for_authorization(DEVICE, BROADCASTER_SCOPES)
    assert fake_time.sleeps == [5, 10]


async def test_code_expires() -> None:
    """If the user never approves, the login stops when the code expires."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"status": 400, "message": "authorization_pending"})

    short = DeviceCode("d", "CODE", "https://twitch.tv/activate", expires_in=12, interval=5)
    with pytest.raises(TwitchAuthError, match="expired"):
        await make_auth(handler).wait_for_authorization(short, BROADCASTER_SCOPES)


# --- refresh and validate -------------------------------------------------------


async def test_refresh_keeps_identity_and_uses_no_secret() -> None:
    """Refreshing sends no client secret and keeps the user id and login."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(form(request))
        return httpx.Response(200, json={"access_token": "new", "refresh_token": "new-ref"})

    old = TwitchTokens("old", "old-ref", ("user:write:chat",), "1001", "nabil")
    fresh = await make_auth(handler).refresh(old)
    assert "client_secret" not in seen
    assert seen["grant_type"] == "refresh_token"
    assert fresh == TwitchTokens("new", "new-ref", ("user:write:chat",), "1001", "nabil")


@pytest.mark.parametrize("status", [400, 401])
async def test_refresh_rejected_means_login_again(status: int) -> None:
    """An invalid refresh token asks the user to log in again."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"status": status, "message": "Invalid refresh token"})

    with pytest.raises(TwitchAuthError, match="log in again"):
        await make_auth(handler).refresh(TwitchTokens("a", "r"))


async def test_validate() -> None:
    """Valid tokens return info; 401 returns None."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] in ("OAuth good", "OAuth bad")
        if request.headers["Authorization"] == "OAuth good":
            return httpx.Response(200, json=VALIDATE_OK)
        return httpx.Response(401, json={"status": 401, "message": "invalid access token"})

    auth = make_auth(handler)
    info = await auth.validate("good")
    assert info is not None
    assert (info.user_id, info.login) == ("1001", "nabil")
    assert await auth.validate("bad") is None


# --- account ------------------------------------------------------------------------


async def test_account_login_saves_tokens() -> None:
    """After login the tokens are in the secret store and the code was shown."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/device"):
            return httpx.Response(
                200,
                json={
                    "device_code": "d",
                    "expires_in": 1800,
                    "interval": 5,
                    "user_code": "ABCDEFGH",
                    "verification_uri": "https://www.twitch.tv/activate",
                },
            )
        if request.url.path.endswith("/validate"):
            return httpx.Response(200, json=VALIDATE_OK)
        return httpx.Response(200, json={"access_token": "acc", "refresh_token": "ref"})

    store = MemoryStore()
    shown: list[str] = []
    account = TwitchAccount(make_auth(handler), store, "twitch.broadcaster")
    await account.login(BROADCASTER_SCOPES, lambda device: shown.append(device.user_code))
    assert shown == ["ABCDEFGH"]
    saved = load_json(store, "twitch.broadcaster")
    assert saved is not None
    assert saved["access_token"] == "acc"
    assert saved["login"] == "nabil"


async def test_account_refreshes_expired_token_and_saves_new_one() -> None:
    """An invalid access token is refreshed and the new (single-use) refresh token saved."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/validate"):
            return httpx.Response(401, json={"message": "invalid access token"})
        return httpx.Response(200, json={"access_token": "new", "refresh_token": "new-ref"})

    store = MemoryStore()
    save_json(store, "k", TwitchTokens("old", "old-ref", (), "1001", "nabil").to_dict())
    account = TwitchAccount(make_auth(handler), store, "k")
    tokens = await account.ensure_valid()
    assert tokens.access_token == "new"
    saved = load_json(store, "k")
    assert saved is not None
    assert saved["refresh_token"] == "new-ref"


async def test_account_not_logged_in() -> None:
    """Without saved tokens, ensure_valid asks for a login."""
    account = TwitchAccount(make_auth(lambda r: httpx.Response(500)), MemoryStore(), "k")
    with pytest.raises(TwitchAuthError, match="log in"):
        await account.ensure_valid()


def test_account_logout_removes_tokens() -> None:
    """Logging out deletes the stored tokens."""
    store = MemoryStore()
    save_json(store, "k", TwitchTokens("a", "r").to_dict())
    account = TwitchAccount(make_auth(lambda r: httpx.Response(500)), store, "k")
    account.logout()
    assert store.get("k") is None


def test_tokens_from_broken_storage() -> None:
    """Incomplete stored data is treated as not logged in."""
    assert TwitchTokens.from_dict({"refresh_token": "r"}) is None
    assert TwitchTokens.from_dict({"access_token": "a", "refresh_token": "r"}) is not None
