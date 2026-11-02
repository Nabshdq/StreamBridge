"""Tests for TikTokSource's connect / wait / reconnect logic (fake client, no network)."""

import asyncio
from collections.abc import Callable, Sequence
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from TikTokLive.client.errors import (
    SignatureRateLimitError,
    UserNotFoundError,
    UserOfflineError,
)
from TikTokLive.events import CommentEvent, ConnectEvent, GiftEvent, LiveEndEvent, SocialEvent

from streambridge.core.events import ConnectionStatus, RelayEvent
from streambridge.sources import tiktok
from streambridge.sources.tiktok import (
    OFFLINE_RECHECK_SECONDS,
    RECONNECT_BACKOFF_SECONDS,
    TikTokSource,
)

# A script step is either an exception to raise from start(), or a list of
# (event type, fake event) pairs the "LIVE" sends before the connection closes.
Step = BaseException | list[tuple[type, Any]]


class StopLoopError(Exception):
    """Raised by the fake sleep to end the endless run loop."""


class FakeClient:
    """Pretends to be a TikTokLiveClient following a script."""

    def __init__(self, step: Step) -> None:
        self.step = step
        self.handlers: dict[type, Callable[[Any], None]] = {}
        self.disconnected = False
        self.web = SimpleNamespace(close=self._close_web)
        self.web_closed = False

    def add_listener(self, event_type: type, handler: Callable[[Any], None]) -> None:
        self.handlers[event_type] = handler

    async def start(self, fetch_live_check: bool = True) -> "asyncio.Task[None]":
        if isinstance(self.step, BaseException):
            raise self.step
        return asyncio.create_task(self._play(self.step))

    async def _play(self, events: list[tuple[type, Any]]) -> None:
        for event_type, event in events:
            if event_type in self.handlers:
                self.handlers[event_type](event)
            await asyncio.sleep(0)

    async def disconnect(self) -> None:
        self.disconnected = True

    async def _close_web(self) -> None:
        self.web_closed = True


class Harness:
    """Runs a TikTokSource against a script and records what it did."""

    def __init__(self, script: Sequence[Step], max_sleeps: int | None = None) -> None:
        self.script = list(script)
        self.max_sleeps = max_sleeps if max_sleeps is not None else len(self.script)
        self.clients: list[FakeClient] = []
        self.sleeps: list[float] = []
        self.statuses: list[tuple[ConnectionStatus, str]] = []
        self.events: list[RelayEvent] = []

    def factory(self, username: str, euler_key: str | None) -> FakeClient:
        self.username, self.euler_key = username, euler_key
        client = FakeClient(self.script[len(self.clients)])
        self.clients.append(client)
        return client

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if len(self.sleeps) >= self.max_sleeps:
            raise StopLoopError

    def run(self, username: str = "@grndpagaming", euler_key: str | None = None) -> None:
        source = TikTokSource(
            username, euler_key=euler_key, client_factory=self.factory, sleep=self.sleep
        )
        with pytest.raises(StopLoopError):
            asyncio.run(source.run(self.events.append, lambda s, d: self.statuses.append((s, d))))

    @property
    def status_names(self) -> list[ConnectionStatus]:
        return [status for status, _ in self.statuses]


def user(name: str = "Budi") -> SimpleNamespace:
    return SimpleNamespace(nickname=name, unique_id=name.lower())


def comment(text: str, name: str = "Budi") -> tuple[type, Any]:
    return CommentEvent, SimpleNamespace(user=user(name), content=text)


CONNECT = (ConnectEvent, SimpleNamespace())
LIVE_END = (LiveEndEvent, SimpleNamespace())


def test_not_live_waits_90_seconds() -> None:
    """When the user is offline the source waits and checks again."""
    harness = Harness([UserOfflineError(), UserOfflineError()])
    harness.run()
    assert harness.sleeps == [OFFLINE_RECHECK_SECONDS, OFFLINE_RECHECK_SECONDS]
    assert harness.status_names == [
        ConnectionStatus.CONNECTING,
        ConnectionStatus.WAITING_LIVE,
        ConnectionStatus.CONNECTING,
        ConnectionStatus.WAITING_LIVE,
    ]
    assert harness.username == "grndpagaming"


def test_events_are_relayed_while_connected() -> None:
    """Comments and finished gifts reach emit; streak taps do not."""
    gift = SimpleNamespace(user=user(), gift=SimpleNamespace(name="Rose"))
    script: list[Step] = [
        [
            CONNECT,
            comment("halo kak"),
            (GiftEvent, SimpleNamespace(**vars(gift), streaking=True, repeat_count=2)),
            (GiftEvent, SimpleNamespace(**vars(gift), streaking=False, repeat_count=5)),
            LIVE_END,
        ]
    ]
    harness = Harness(script)
    harness.run()
    assert [(e.kind, e.text, e.gift_count) for e in harness.events] == [
        ("chat", "halo kak", 1),
        ("gift", "", 5),
    ]
    assert ConnectionStatus.CONNECTED in harness.status_names


def test_live_end_goes_back_to_waiting() -> None:
    """After the LIVE ends, the source waits for the next LIVE and reconnects."""
    script: list[Step] = [[CONNECT, comment("satu"), LIVE_END], [CONNECT, comment("dua")]]
    harness = Harness(script, max_sleeps=2)
    harness.run()
    assert harness.sleeps[0] == OFFLINE_RECHECK_SECONDS
    assert harness.status_names[:4] == [
        ConnectionStatus.CONNECTING,
        ConnectionStatus.CONNECTED,
        ConnectionStatus.WAITING_LIVE,
        ConnectionStatus.CONNECTING,
    ]
    assert [e.text for e in harness.events] == ["satu", "dua"]


def test_errors_back_off_5_10_30_60_60() -> None:
    """Repeated failures wait longer each time, capped at 60 s."""
    errors: list[Step] = [httpx.ConnectError("no internet") for _ in range(5)]
    harness = Harness(errors)
    harness.run()
    assert harness.sleeps == [*RECONNECT_BACKOFF_SECONDS, RECONNECT_BACKOFF_SECONDS[-1]]
    assert ConnectionStatus.DISCONNECTED in harness.status_names


def test_backoff_resets_after_a_successful_connection() -> None:
    """After connecting once, the next failure starts again at 5 s."""
    script: list[Step] = [
        httpx.ConnectError("x"),
        httpx.ConnectError("x"),
        [CONNECT, comment("halo")],  # connected, then the connection drops
        httpx.ConnectError("x"),
    ]
    harness = Harness(script)
    harness.run()
    assert harness.sleeps == [5.0, 10.0, 5.0, 10.0]


def test_tiktok_refusals_are_reported_as_errors() -> None:
    """Blocked / rate limited / not found show an error with an explanation."""
    script: list[Step] = [
        UserNotFoundError("grndpagaming"),
        SignatureRateLimitError(
            "limit",
            "retry in %s s",
            response=httpx.Response(429, headers={"RateLimit-Remaining": "30"}),
        ),
    ]
    harness = Harness(script)
    harness.run()
    errors = [detail for status, detail in harness.statuses if status == ConnectionStatus.ERROR]
    assert "no LIVE access" in errors[0]
    assert "Euler API key" in errors[1]


def test_every_attempt_uses_a_fresh_client_and_closes_it() -> None:
    """Each attempt gets a new client, and every client is closed."""
    harness = Harness([UserOfflineError(), [CONNECT, LIVE_END], httpx.ConnectError("x")])
    harness.run()
    assert len(harness.clients) == 3
    assert all(client.disconnected and client.web_closed for client in harness.clients)


def test_euler_key_is_passed_to_the_client() -> None:
    """The optional API key reaches the client factory."""
    harness = Harness([UserOfflineError()])
    harness.run(euler_key="secret-key")
    assert harness.euler_key == "secret-key"


def test_bad_event_does_not_break_the_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """If handling one event fails, the next events still arrive."""
    original = tiktok.map_comment

    def flaky(event: Any) -> RelayEvent | None:
        if event.content == "boom":
            raise ValueError("bad data")
        return original(event)

    monkeypatch.setattr(tiktok, "map_comment", flaky)
    harness = Harness([[CONNECT, comment("boom"), comment("masih jalan"), LIVE_END]])
    harness.run()
    assert [e.text for e in harness.events] == ["masih jalan"]


def test_raw_social_data_goes_to_listener() -> None:
    """Raw follow/share data is reported for investigating reposts."""
    raw: list[dict[str, Any]] = []
    common = SimpleNamespace(display_text=SimpleNamespace(key="pm_mt_guidance_share"))
    script: list[Step] = [
        [CONNECT, (SocialEvent, SimpleNamespace(user=user(), common=common, share_type=1))]
    ]
    harness = Harness(script)
    source = TikTokSource(
        "grndpagaming",
        client_factory=harness.factory,
        sleep=harness.sleep,
        raw_listener=raw.append,
    )
    with pytest.raises(StopLoopError):
        asyncio.run(source.run(harness.events.append, lambda s, d: None))
    assert raw[0]["key"] == "pm_mt_guidance_share"
    assert harness.events[0].kind == "share"


def test_handlers_register_on_a_real_tiktoklive_client() -> None:
    """Regression: registering on the real client must not crash (no network used)."""

    async def scenario() -> None:
        client = tiktok.create_client("grndpagaming", None)
        source = TikTokSource("grndpagaming")
        source._add_handlers(client, lambda e: None, lambda s, d: None, tiktok._AttemptState())
        try:
            for event_type in (CommentEvent, GiftEvent, SocialEvent, ConnectEvent, LiveEndEvent):
                assert client.has_listener(event_type)
        finally:
            await client.web.close()

    asyncio.run(scenario())


def test_setup_failure_is_retried_not_fatal() -> None:
    """If preparing a connection fails, the source backs off and tries again."""

    class BrokenClient(FakeClient):
        def add_listener(self, event_type: type, handler: Callable[[Any], None]) -> None:
            raise AttributeError("library changed")

    harness = Harness([[], []], max_sleeps=2)
    harness.factory = lambda username, key: BrokenClient([])  # type: ignore[method-assign]
    harness.run()
    assert harness.sleeps == [5.0, 10.0]
    assert harness.status_names.count(ConnectionStatus.ERROR) == 2


def test_stop_closes_the_client() -> None:
    """Cancelling the source (Stop) closes the open connection."""

    class EndlessClient(FakeClient):
        async def _play(self, events: list[tuple[type, Any]]) -> None:
            await asyncio.Event().wait()

    clients: list[FakeClient] = []

    def factory(username: str, euler_key: str | None) -> FakeClient:
        client = EndlessClient([])
        clients.append(client)
        return client

    async def scenario() -> None:
        source = TikTokSource("grndpagaming", client_factory=factory)
        task = asyncio.create_task(source.run(lambda e: None, lambda s, d: None))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert clients[0].disconnected
    assert clients[0].web_closed
