"""Tests for the bridge between the engine thread and the UI."""

from __future__ import annotations

import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from streambridge.core.assembly import SetupError  # noqa: E402
from streambridge.core.events import ConnectionStatus  # noqa: E402
from streambridge.core.pipeline import Counters  # noqa: E402
from streambridge.ui.bridge import SOURCE_ID, Backend  # noqa: E402


@pytest.fixture(scope="module")
def app():
    """One Qt application for all tests in this file."""
    return QGuiApplication.instance() or QGuiApplication([])


class FakeEngine:
    """Stands in for RelayEngine: records calls and lets tests fire listener events."""

    def __init__(self, listener) -> None:
        self.listener = listener
        self.started = False
        self.stop_thread: str | None = None
        self.stop_delay = 0.0

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stop_thread = threading.current_thread().name
        time.sleep(self.stop_delay)
        self.listener.on_stopped()


def pump(app, until=lambda: False, timeout: float = 3.0) -> None:
    """Run the Qt event loop until ``until()`` is true or the timeout passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if until():
            return
        time.sleep(0.005)
    app.processEvents()


def make_backend(app, **engine_options):
    """Build a Backend whose factory hands out FakeEngines; return both."""
    engines: list[FakeEngine] = []

    def factory(listener):
        engine = FakeEngine(listener)
        for name, value in engine_options.items():
            setattr(engine, name, value)
        engines.append(engine)
        return engine

    return Backend(factory, connection_ids=(SOURCE_ID, "twitch")), engines


def card(backend: Backend, connection_id: str) -> dict:
    return next(c for c in backend.connections if c["id"] == connection_id)


def test_starts_idle(app):
    backend, _ = make_backend(app)
    assert not backend.running
    assert not backend.stopping
    assert all(c["status"] == "stopped" for c in backend.connections)


def test_start_builds_and_starts_an_engine(app):
    backend, engines = make_backend(app)
    backend.start()
    assert backend.running
    assert engines[0].started
    assert all(c["status"] == "connecting" for c in backend.connections)


def test_start_twice_builds_only_one_engine(app):
    backend, engines = make_backend(app)
    backend.start()
    backend.start()
    assert len(engines) == 1


def test_setup_error_is_shown_and_nothing_runs(app):
    def factory(listener):
        raise SetupError(["Enter a TikTok username", "Log in to Twitch"])

    backend = Backend(factory)
    backend.start()
    assert not backend.running
    assert "Enter a TikTok username" in backend.lastError
    assert "Log in to Twitch" in backend.lastError


def test_unexpected_error_does_not_crash_the_ui(app):
    def factory(listener):
        raise RuntimeError("boom")

    backend = Backend(factory)
    backend.start()
    assert not backend.running
    assert backend.lastError == "boom"


def test_status_events_update_the_cards(app):
    backend, engines = make_backend(app)
    backend.start()
    # Fire from another thread, like the real engine does.
    worker = threading.Thread(
        target=lambda: (
            engines[0].listener.on_source_status(ConnectionStatus.CONNECTED, "@someone"),
            engines[0].listener.on_destination_status("twitch", ConnectionStatus.ERROR, "no"),
        )
    )
    worker.start()
    worker.join()
    pump(app, lambda: card(backend, SOURCE_ID)["status"] == "connected")
    assert card(backend, SOURCE_ID)["detail"] == "@someone"
    assert card(backend, "twitch")["status"] == "error"


def test_messages_reach_the_feed(app):
    backend, engines = make_backend(app)
    backend.start()
    engines[0].listener.on_message_sent("twitch", "hello")
    engines[0].listener.on_message_rejected("twitch", "bad", "too long")
    pump(app, lambda: backend.feed.rowCount() == 2)
    assert backend.feed.row_at(0).status == "sent"
    assert backend.feed.row_at(1).status == "rejected"
    assert backend.feed.row_at(1).reason == "too long"


def test_counters_are_summed_across_destinations(app):
    backend, engines = make_backend(app)
    backend.start()
    counters = Counters()
    counters.sent = {"twitch": 3, "youtube": 4}
    counters.filtered = 2
    counters.dropped = {"youtube": 1}
    counters.waiting = {"twitch": 5}
    engines[0].listener.on_counters(counters)
    pump(app, lambda: backend.sentCount == 7)
    assert backend.sentCount == 7
    assert backend.filteredCount == 2
    assert backend.droppedCount == 1
    assert backend.waitingCount == 5


def test_engine_errors_become_last_error(app):
    backend, engines = make_backend(app)
    backend.start()
    engines[0].listener.on_error("twitch", "token expired")
    pump(app, lambda: backend.lastError != "")
    assert backend.lastError == "twitch: token expired"


def test_stop_does_not_block_the_ui_thread(app):
    backend, engines = make_backend(app, stop_delay=0.5)
    backend.start()
    began = time.monotonic()
    backend.stop()
    assert time.monotonic() - began < 0.2  # returned long before the engine finished
    assert backend.stopping
    pump(app, lambda: not backend.running)
    assert not backend.running
    assert not backend.stopping
    assert engines[0].stop_thread != threading.main_thread().name
    assert all(c["status"] == "stopped" for c in backend.connections)


def test_can_start_again_after_stop(app):
    backend, engines = make_backend(app)
    backend.start()
    backend.stop()
    pump(app, lambda: not backend.running)
    backend.start()
    assert backend.running
    assert len(engines) == 2


def test_a_flood_from_the_engine_thread_keeps_the_feed_bounded(app):
    backend, engines = make_backend(app)
    backend.start()

    def flood():
        for number in range(3000):
            engines[0].listener.on_message_sent("twitch", f"message {number}")

    worker = threading.Thread(target=flood)
    worker.start()
    worker.join()
    pump(
        app,
        lambda: backend.feed.rowCount() == 200 and backend.feed.row_at(199).text.endswith("2999"),
    )
    assert backend.feed.rowCount() == 200
    assert backend.feed.row_at(199).text == "message 2999"


def test_real_engine_with_fake_source_drives_the_whole_ui_state(app):
    """Start the real RelayEngine (fake TikTok events) and watch the Backend follow it."""
    from streambridge.app import FAKE_CONNECTIONS, fake_engine_factory

    backend = Backend(fake_engine_factory(), FAKE_CONNECTIONS)
    backend.start()
    assert backend.lastError == ""
    pump(app, lambda: backend.sentCount > 0 and backend.feed.rowCount() > 0, timeout=8.0)
    assert backend.feed.rowCount() > 0
    assert backend.sentCount > 0
    assert all(c["status"] != "connecting" for c in backend.connections)

    began = time.monotonic()
    backend.stop()
    assert time.monotonic() - began < 0.2
    pump(app, lambda: not backend.running, timeout=10.0)
    assert not backend.running
    assert all(c["status"] == "stopped" for c in backend.connections)


def test_counters_and_feed_are_cleared_when_starting_again(app):
    backend, engines = make_backend(app)
    backend.start()
    counters = Counters()
    counters.sent = {"twitch": 3}
    counters.waiting = {"twitch": 2}
    engines[0].listener.on_counters(counters)
    engines[0].listener.on_message_sent("twitch", "hello")
    pump(app, lambda: backend.sentCount == 3 and backend.feed.rowCount() == 1)
    backend.stop()
    pump(app, lambda: not backend.running)
    assert backend.waitingCount == 2  # the last numbers stay visible after Stop

    backend.start()
    assert backend.sentCount == 0
    assert backend.waitingCount == 0
    assert backend.feed.rowCount() == 0
