"""Tests for the Twitch destination against a simulated Twitch (no network)."""

import asyncio
import json
from typing import Any

import httpx
import pytest

from streambridge.auth.twitch_device import TwitchAuthError, TwitchSetupError, TwitchTokens
from streambridge.core.config import EventToggles
from streambridge.core.engine import DestinationSetup, EngineSettings, RelayEngine
from streambridge.core.events import RelayEvent
from streambridge.core.ratelimit import TWITCH_RULES
from streambridge.core.secrets import MemoryStore, load_json, save_json
from streambridge.destinations.base import TemporarySendError
from streambridge.destinations.twitch import (
    REASON_FORBIDDEN,
    REASON_LOGIN_EXPIRED,
    NotModeratorError,
    TwitchDestination,
)

KEY = "twitch.broadcaster"


class FakeTwitch:
    """A tiny in-memory Twitch: tokens, users, moderators and chat."""

    def __init__(self) -> None:
        self.valid_tokens = {"acc": ("1001", "nabil")}
        self.refresh_tokens = {"ref": "acc2"}
        self.users = {"streamer": "2002", "nabil": "1001"}
        self.moderates: dict[str, list[str]] = {"1001": []}
        self.page_size = 100
        self.chat_status: list[int] = []  # next status codes for chat posts
        self.drop: dict[str, str] | None = None
        self.sent: list[dict[str, Any]] = []
        self.validations = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/oauth2/validate":
            return self._validate(request)
        if path == "/oauth2/token":
            return self._refresh(request)
        if not self._authorized(request):
            return httpx.Response(401, json={"message": "invalid access token"})
        if path == "/helix/users":
            login = request.url.params["login"]
            found = [{"id": self.users[login], "login": login}] if login in self.users else []
            return httpx.Response(200, json={"data": found})
        if path == "/helix/moderation/channels":
            return self._moderated(request)
        if path == "/helix/chat/messages":
            return self._chat(request)
        return httpx.Response(404)

    def _token(self, request: httpx.Request) -> str:
        return request.headers.get("Authorization", "").split(" ", 1)[-1]

    def _authorized(self, request: httpx.Request) -> bool:
        return self._token(request) in self.valid_tokens

    def _validate(self, request: httpx.Request) -> httpx.Response:
        self.validations += 1
        token = self._token(request)
        if token not in self.valid_tokens:
            return httpx.Response(401, json={"message": "invalid access token"})
        user_id, login = self.valid_tokens[token]
        return httpx.Response(
            200,
            json={"user_id": user_id, "login": login, "scopes": [], "expires_in": 9999},
        )

    def _refresh(self, request: httpx.Request) -> httpx.Response:
        refresh = dict(x.split("=") for x in request.content.decode().split("&"))["refresh_token"]
        if refresh not in self.refresh_tokens:
            return httpx.Response(400, json={"message": "Invalid refresh token"})
        new_access = self.refresh_tokens.pop(refresh)
        self.valid_tokens[new_access] = ("1001", "nabil")
        return httpx.Response(200, json={"access_token": new_access, "refresh_token": "ref2"})

    def _moderated(self, request: httpx.Request) -> httpx.Response:
        ids = self.moderates.get(request.url.params["user_id"], [])
        start = int(request.url.params.get("after", "0"))
        page = ids[start : start + self.page_size]
        more = start + self.page_size < len(ids)
        return httpx.Response(
            200,
            json={
                "data": [{"broadcaster_id": i} for i in page],
                "pagination": {"cursor": str(start + self.page_size)} if more else {},
            },
        )

    def _chat(self, request: httpx.Request) -> httpx.Response:
        if self.chat_status:
            status = self.chat_status.pop(0)
            if status != 200:
                return httpx.Response(status, json={"message": f"status {status}"})
        body = json.loads(request.content)
        if self.drop:
            return httpx.Response(
                200, json={"data": [{"message_id": "", "is_sent": False, "drop_reason": self.drop}]}
            )
        self.sent.append(body)
        return httpx.Response(200, json={"data": [{"message_id": "m1", "is_sent": True}]})


async def no_sleep(seconds: float) -> None:
    """Never actually wait in tests."""
    await asyncio.sleep(0)


def make_destination(
    twitch: FakeTwitch,
    store: MemoryStore | None = None,
    bot_mode: bool = False,
    channel: str = "",
    access: str = "acc",
) -> TwitchDestination:
    """A destination wired to the fake Twitch with saved tokens."""
    if store is None:
        store = MemoryStore()
        save_json(store, KEY, TwitchTokens(access, "ref", (), "1001", "nabil").to_dict())
    return TwitchDestination(
        "client-id",
        store,
        KEY,
        channel=channel,
        bot_mode=bot_mode,
        transport=httpx.MockTransport(twitch),
        sleep=no_sleep,
        validate_interval=3600,
    )


async def started(destination: TwitchDestination) -> TwitchDestination:
    """Start a destination (helper for one-liners)."""
    await destination.start()
    return destination


# --- start ----------------------------------------------------------------------------


async def test_streamer_mode_sends_to_own_channel() -> None:
    """Without a bot, messages go to the logged-in streamer's channel."""
    twitch = FakeTwitch()
    destination = await started(make_destination(twitch))
    result = await destination.send("💬 [TikTok] Budi: halo")
    await destination.stop()
    assert result.ok
    assert twitch.sent == [
        {"broadcaster_id": "1001", "sender_id": "1001", "message": "💬 [TikTok] Budi: halo"}
    ]


async def test_not_logged_in() -> None:
    """Start fails with a login message when no tokens are saved."""
    destination = make_destination(FakeTwitch(), store=MemoryStore())
    with pytest.raises(TwitchAuthError):
        await destination.start()
    await destination.stop()


async def test_bot_mode_requires_moderator() -> None:
    """A bot that is not a moderator cannot start, and the message says how to fix it."""
    twitch = FakeTwitch()
    destination = make_destination(twitch, bot_mode=True, channel="@Streamer")
    with pytest.raises(NotModeratorError, match="/mod nabil"):
        await destination.start()
    await destination.stop()


async def test_bot_mode_moderator_found_on_second_page() -> None:
    """Moderator status is found even when the list has several pages."""
    twitch = FakeTwitch()
    twitch.page_size = 2
    twitch.moderates["1001"] = ["9", "8", "7", "2002"]
    destination = await started(make_destination(twitch, bot_mode=True, channel="streamer"))
    await destination.send("halo")
    await destination.stop()
    assert twitch.sent[0]["broadcaster_id"] == "2002"
    assert twitch.sent[0]["sender_id"] == "1001"


async def test_bot_mode_unknown_channel() -> None:
    """A misspelled channel gives a clear error."""
    destination = make_destination(FakeTwitch(), bot_mode=True, channel="nobody")
    with pytest.raises(TwitchSetupError, match="not found"):
        await destination.start()
    await destination.stop()


async def test_expired_token_is_refreshed_on_start() -> None:
    """An expired access token is refreshed during start and the new one saved."""
    twitch = FakeTwitch()
    store = MemoryStore()
    save_json(store, KEY, TwitchTokens("expired", "ref", (), "1001", "nabil").to_dict())
    destination = await started(make_destination(twitch, store=store))
    await destination.stop()
    saved = load_json(store, KEY)
    assert saved is not None
    assert (saved["access_token"], saved["refresh_token"]) == ("acc2", "ref2")


# --- send -------------------------------------------------------------------------------


async def test_automod_drop_is_reported() -> None:
    """is_sent=false gives a refused result with Twitch's reason."""
    twitch = FakeTwitch()
    twitch.drop = {"code": "msg_rejected", "message": "Your message is being checked by mods"}
    destination = await started(make_destination(twitch))
    result = await destination.send("halo")
    await destination.stop()
    assert not result.ok
    assert result.reason == "Your message is being checked by mods"


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_rate_limit_and_server_errors_are_temporary(status: int) -> None:
    """429 and 5xx make the engine retry (nothing is dropped)."""
    twitch = FakeTwitch()
    twitch.chat_status = [status]
    destination = await started(make_destination(twitch))
    with pytest.raises(TemporarySendError):
        await destination.send("halo")
    await destination.stop()


async def test_network_error_is_temporary() -> None:
    """A lost connection is retried by the engine."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/helix/chat/messages":
            raise httpx.ConnectError("no internet")
        return FakeTwitch()(request)

    store = MemoryStore()
    save_json(store, KEY, TwitchTokens("acc", "ref", (), "1001", "nabil").to_dict())
    destination = TwitchDestination(
        "client-id", store, KEY, transport=httpx.MockTransport(handler), sleep=no_sleep
    )
    await destination.start()
    with pytest.raises(TemporarySendError):
        await destination.send("halo")
    await destination.stop()


async def test_401_refreshes_once_then_sends() -> None:
    """A token that expires mid-stream is refreshed and the message still goes out."""
    twitch = FakeTwitch()
    destination = await started(make_destination(twitch))
    del twitch.valid_tokens["acc"]  # the token expires during the stream
    result = await destination.send("halo")
    await destination.stop()
    assert result.ok
    assert twitch.sent[0]["message"] == "halo"


async def test_401_with_dead_refresh_token_asks_for_login() -> None:
    """If refreshing also fails, the message is refused with a login hint."""
    twitch = FakeTwitch()
    destination = await started(make_destination(twitch))
    del twitch.valid_tokens["acc"]
    twitch.refresh_tokens.clear()
    result = await destination.send("halo")
    await destination.stop()
    assert result.reason == REASON_LOGIN_EXPIRED


async def test_403_hints_at_lost_moderator_role() -> None:
    """403 is refused with a hint about the moderator role."""
    twitch = FakeTwitch()
    twitch.chat_status = [403]
    destination = await started(make_destination(twitch))
    result = await destination.send("halo")
    await destination.stop()
    assert result.reason == REASON_FORBIDDEN


async def test_hourly_validation_checks_the_login() -> None:
    """validate_once contacts Twitch's validate endpoint."""
    twitch = FakeTwitch()
    destination = await started(make_destination(twitch))
    before = twitch.validations
    await destination.validate_once()
    await destination.stop()
    assert twitch.validations == before + 1


def test_twitch_limits() -> None:
    """Twitch keeps every message (no queue limit) and uses the 80/30 s rule."""
    destination = make_destination(FakeTwitch())
    assert destination.max_queue_size is None
    assert destination.rate_rules == TWITCH_RULES
    assert destination.max_length == 500


# --- with the engine ------------------------------------------------------------------


def test_engine_relays_to_fake_twitch() -> None:
    """End to end: a TikTok-like event reaches the (fake) Twitch chat via the engine."""
    from tests.test_engine import ListSource, wait_until

    twitch = FakeTwitch()
    destination = make_destination(twitch)
    event = RelayEvent(kind="gift", platform="tiktok", user="Budi", gift_name="Rose", gift_count=3)
    engine = RelayEngine(
        ListSource([event]),
        [DestinationSetup(destination, EventToggles().as_dict())],
        EngineSettings(relay_language="id", gift_delay=0.05, tick_interval=0.01),
    )
    engine.start()
    wait_until(lambda: bool(twitch.sent))
    engine.stop()
    assert twitch.sent[0]["message"] == "🎁 [TikTok] Budi mengirim Rose 🌹 x3"
