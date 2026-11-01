"""Tests for the RelayEngine (real thread, short timings)."""

import asyncio
import threading
import time
from collections.abc import Callable, Sequence

import pytest

from streambridge.core import engine as engine_module
from streambridge.core.config import EventToggles
from streambridge.core.engine import DestinationSetup, EngineListener, EngineSettings, RelayEngine
from streambridge.core.events import ConnectionStatus, RelayEvent
from streambridge.core.pipeline import Counters
from streambridge.core.ratelimit import RateRule
from streambridge.destinations.base import Destination, SendResult, TemporarySendError
from streambridge.sources.base import EmitEvent, ReportStatus, Source

FAST = EngineSettings(
    relay_language="en",
    gift_delay=0.05,
    tick_interval=0.01,
    counters_interval=0.05,
    stop_grace=1.0,
)


class ListSource(Source):
    """Emits a fixed list of events, then stays connected."""

    name = "list"

    def __init__(self, events: Sequence[RelayEvent]) -> None:
        self.events = list(events)

    async def run(self, emit: EmitEvent, report_status: ReportStatus) -> None:
        report_status(ConnectionStatus.CONNECTED, "")
        for event in self.events:
            emit(event)
        await asyncio.Event().wait()


class RecordingDestination(Destination):
    """Remembers what it was asked to send; can fail on purpose."""

    def __init__(
        self,
        name: str = "rec",
        temporary_failures: int = 0,
        refuse: bool = False,
        fail_start: bool = False,
        rate_rules: Sequence[RateRule] = (),
    ) -> None:
        self.name = name
        self.max_length = 500
        self.rate_rules = tuple(rate_rules)
        self.max_queue_size = None
        self.sent: list[str] = []
        self.attempts = 0
        self.temporary_failures = temporary_failures
        self.refuse = refuse
        self.fail_start = fail_start
        self.stopped = False

    async def start(self) -> None:
        if self.fail_start:
            raise RuntimeError("cannot log in")

    async def send(self, text: str) -> SendResult:
        self.attempts += 1
        if self.attempts <= self.temporary_failures:
            raise TemporarySendError("network down")
        if self.refuse:
            return SendResult(ok=False, reason="automod")
        self.sent.append(text)
        return SendResult(ok=True)

    async def stop(self) -> None:
        self.stopped = True


class RecordingListener(EngineListener):
    """Collects listener calls."""

    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.rejected: list[tuple[str, str, str]] = []
        self.statuses: list[tuple[str, ConnectionStatus]] = []
        self.counters: Counters | None = None
        self.stopped = threading.Event()

    def on_destination_status(self, name: str, status: ConnectionStatus, detail: str) -> None:
        self.statuses.append((name, status))

    def on_message_rejected(self, destination: str, text: str, reason: str) -> None:
        self.rejected.append((destination, text, reason))

    def on_error(self, where: str, message: str) -> None:
        self.errors.append((where, message))

    def on_counters(self, counters: Counters) -> None:
        self.counters = counters

    def on_stopped(self) -> None:
        self.stopped.set()


def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> None:
    """Wait until ``condition()`` is true or fail the test."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    pytest.fail("condition not reached in time")


def ev(kind: str, user: str = "Budi", **values: object) -> RelayEvent:
    """Make an event."""
    return RelayEvent(kind=kind, platform="tiktok", user=user, **values)


def setup_for(destination: Destination, compact: bool = False) -> DestinationSetup:
    """Every event kind enabled."""
    return DestinationSetup(destination, EventToggles().as_dict(), compact_mode=compact)


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry quickly in tests."""
    monkeypatch.setattr(engine_module, "RETRY_DELAYS", (0.01,))


def test_relays_events_end_to_end() -> None:
    """Chat, follow and a gift streak arrive formatted at the destination."""
    destination = RecordingDestination()
    events = [
        ev("chat", text="halo"),
        ev("follow", user="Sari"),
        ev("gift", gift_name="Rose"),
        ev("gift", gift_name="Rose"),
    ]
    listener = RecordingListener()
    engine = RelayEngine(ListSource(events), [setup_for(destination)], FAST, listener)
    engine.start()
    wait_until(lambda: len(destination.sent) == 3)
    engine.stop()
    assert listener.stopped.is_set()
    assert not engine.is_running
    assert destination.stopped
    assert set(destination.sent) == {
        "💬 [TikTok] Budi: halo",
        "⭐ [TikTok] Sari followed",
        "🎁 [TikTok] Budi sent Rose 🌹 x2",
    }
    assert listener.counters is not None
    assert listener.counters.sent["rec"] == 3


def test_temporary_errors_are_retried_until_sent() -> None:
    """Twitch rule: nothing is lost when the network blips."""
    destination = RecordingDestination(temporary_failures=3)
    engine = RelayEngine(ListSource([ev("chat", text="penting")]), [setup_for(destination)], FAST)
    engine.start()
    wait_until(lambda: destination.sent == ["💬 [TikTok] Budi: penting"])
    engine.stop()
    assert destination.attempts == 4


def test_refused_message_is_counted_and_reported() -> None:
    """A platform refusal is shown, not retried."""
    destination = RecordingDestination(refuse=True)
    listener = RecordingListener()
    engine = RelayEngine(
        ListSource([ev("chat", text="halo")]), [setup_for(destination)], FAST, listener
    )
    engine.start()
    wait_until(lambda: bool(listener.rejected))
    engine.stop()
    assert listener.rejected[0][2] == "automod"
    assert engine.counters.rejected["rec"] == 1
    assert destination.attempts == 1


def test_failing_destination_does_not_block_the_other() -> None:
    """If one destination cannot start, the other still relays."""
    broken = RecordingDestination(name="broken", fail_start=True)
    working = RecordingDestination(name="working")
    listener = RecordingListener()
    engine = RelayEngine(
        ListSource([ev("chat", text="halo")]),
        [setup_for(broken), setup_for(working)],
        FAST,
        listener,
    )
    engine.start()
    wait_until(lambda: len(working.sent) == 1)
    engine.stop()
    assert ("broken", ConnectionStatus.ERROR) in listener.statuses
    assert listener.errors[0][0] == "broken"
    assert broken.sent == []


def test_stop_sends_held_gifts() -> None:
    """Gifts still inside their merge window are sent on stop, not dropped."""
    destination = RecordingDestination()
    slow_gifts = EngineSettings(relay_language="en", gift_delay=60.0, tick_interval=0.01)
    engine = RelayEngine(
        ListSource([ev("gift", gift_name="Galaxy")]), [setup_for(destination)], slow_gifts
    )
    engine.start()
    time.sleep(0.1)
    assert destination.sent == []
    engine.stop()
    assert destination.sent == ["🎁 [TikTok] Budi sent Galaxy 🌌 x1"]


def test_stop_counts_chat_that_was_not_sent() -> None:
    """Chat still waiting at stop is counted, so nothing disappears silently."""
    destination = RecordingDestination(rate_rules=[RateRule(1, 60.0)])
    events = [ev("chat", user=f"viewer{number}", text=f"pesan {number}") for number in range(5)]
    engine = RelayEngine(ListSource(events), [setup_for(destination)], FAST)
    engine.start()
    wait_until(lambda: len(destination.sent) == 1)
    engine.stop()
    assert len(destination.sent) + engine.counters.unsent_on_stop == 5


def test_send_test_message() -> None:
    """The UI's test button reaches every destination."""
    destination = RecordingDestination()
    engine = RelayEngine(ListSource([]), [setup_for(destination)], FAST)
    engine.start()
    wait_until(lambda: engine._pipeline is not None)
    engine.send_test_message("StreamBridge test ✅")
    wait_until(lambda: destination.sent == ["StreamBridge test ✅"])
    engine.stop()


def test_engine_can_restart() -> None:
    """Start -> stop -> start works and counters start fresh."""
    destination = RecordingDestination()
    engine = RelayEngine(ListSource([ev("follow")]), [setup_for(destination)], FAST)
    for _ in range(2):
        engine.start()
        wait_until(lambda: engine.counters.sent.get("rec") == 1)
        engine.stop()
    assert len(destination.sent) == 2
