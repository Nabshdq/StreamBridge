"""Tests for changing settings while the relay runs (reload_config)."""

import asyncio
import queue

from streambridge.core.config import EventToggles
from streambridge.core.engine import (
    DestinationSetup,
    EngineSettings,
    RelayEngine,
    RouteOptions,
)
from streambridge.core.events import ConnectionStatus, RelayEvent
from streambridge.sources.base import EmitEvent, ReportStatus, Source
from tests.test_engine import FAST, RecordingDestination, wait_until


class ManualSource(Source):
    """Emits events the test puts in, whenever it puts them in."""

    name = "manual"

    def __init__(self) -> None:
        self.pending: queue.Queue[RelayEvent] = queue.Queue()

    async def run(self, emit: EmitEvent, report_status: ReportStatus) -> None:
        report_status(ConnectionStatus.CONNECTED, "")
        while True:
            try:
                emit(self.pending.get_nowait())
            except queue.Empty:
                await asyncio.sleep(0.01)


def chat(text: str, user: str = "Budi") -> RelayEvent:
    """A chat event."""
    return RelayEvent(kind="chat", platform="tiktok", user=user, text=text)


def follow(user: str = "Sari") -> RelayEvent:
    """A follow event."""
    return RelayEvent(kind="follow", platform="tiktok", user=user)


def all_on() -> dict[str, bool]:
    """Every event kind enabled."""
    return EventToggles().as_dict()


def start_engine(compact: bool = False) -> tuple[RelayEngine, ManualSource, RecordingDestination]:
    """A running engine with one recording destination."""
    source, destination = ManualSource(), RecordingDestination()
    setup = DestinationSetup(destination, all_on(), compact_mode=compact)
    engine = RelayEngine(source, [setup], FAST)
    engine.start()
    wait_until(lambda: engine._pipeline is not None)
    return engine, source, destination


def test_language_and_toggles_change_while_running() -> None:
    """After a reload, new events use the new language and toggles."""
    engine, source, destination = start_engine()
    source.pending.put(follow())
    wait_until(lambda: destination.sent == ["⭐ [TikTok] Sari followed"])

    no_chat = {**all_on(), "chat": False}
    engine.reload_config(
        EngineSettings(relay_language="id", tick_interval=0.01, gift_delay=0.05),
        {"rec": RouteOptions(toggles=no_chat)},
    )
    source.pending.put(chat("tidak dikirim"))
    source.pending.put(follow("Andi"))
    wait_until(lambda: len(destination.sent) == 2)
    engine.stop()
    assert destination.sent[1] == "⭐ [TikTok] Andi mulai mengikuti"


def test_custom_template_applies_after_reload() -> None:
    """A template written in Settings is used without restarting."""
    engine, source, destination = start_engine()
    engine.reload_config(FAST, {"rec": RouteOptions(all_on(), {"chat": "{user} >> {message}"})})
    source.pending.put(chat("halo"))
    wait_until(lambda: destination.sent == ["Budi >> halo"])
    engine.stop()


def test_rude_word_list_change_applies() -> None:
    """New rude words from Settings are censored right away."""
    engine, source, destination = start_engine()
    engine.reload_config(
        EngineSettings(relay_language="en", rude_words=("kampret",), tick_interval=0.01),
        {"rec": RouteOptions(all_on())},
    )
    source.pending.put(chat("dasar kampret"))
    wait_until(lambda: destination.sent == ["💬 [TikTok] Budi: dasar k*****t"])
    engine.stop()


def test_turning_compact_off_sends_collected_chat() -> None:
    """Chat already collected for a batch is sent, not lost, when compact mode is turned off."""
    engine, source, destination = start_engine(compact=True)
    source.pending.put(chat("satu"))
    wait_until(
        lambda: (
            engine._active[0].route.batcher is not None
            and len(engine._active[0].route.batcher) == 1
        )
    )
    engine.reload_config(FAST, {"rec": RouteOptions(all_on(), compact_mode=False)})
    wait_until(lambda: destination.sent == ["💬 TikTok: Budi: satu"])
    source.pending.put(chat("dua", user="Sari"))
    wait_until(lambda: len(destination.sent) == 2)
    engine.stop()
    assert destination.sent[1] == "💬 [TikTok] Sari: dua"


def test_reload_keeps_collected_chat_when_compact_stays_on() -> None:
    """Reloading other settings does not throw away chat waiting in a batch."""
    engine, source, destination = start_engine(compact=True)
    source.pending.put(chat("tetap ada"))
    wait_until(lambda: len(engine._active[0].route.batcher or []) == 1)
    batcher_before = engine._active[0].route.batcher
    new_settings = EngineSettings(relay_language="id", tick_interval=0.01)
    engine.reload_config(new_settings, {"rec": RouteOptions(all_on(), compact_mode=True)})
    wait_until(lambda: engine._settings is new_settings)
    batcher_after = engine._active[0].route.batcher
    engine.stop()
    assert batcher_after is batcher_before  # same batcher, collected line kept
    # On stop the batch is flushed into the queue; chat is not given grace time,
    # so it is counted as "not sent (stopped)" rather than silently lost.
    assert len(destination.sent) + engine.counters.unsent_on_stop == 1


def test_reload_while_stopped_is_used_on_next_start() -> None:
    """Settings changed while stopped apply when the relay starts."""
    source, destination = ManualSource(), RecordingDestination()
    engine = RelayEngine(source, [DestinationSetup(destination, all_on())], FAST)
    engine.reload_config(
        EngineSettings(relay_language="id", tick_interval=0.01),
        {"rec": RouteOptions({**all_on(), "follow": True})},
    )
    engine.start()
    source.pending.put(follow())
    wait_until(lambda: destination.sent == ["⭐ [TikTok] Sari mulai mengikuti"])
    engine.stop()
