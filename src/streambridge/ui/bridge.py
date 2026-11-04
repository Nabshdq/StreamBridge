"""The bridge between the relay engine (its own thread) and the QML screens.

The engine reports what happens through ``EngineListener`` callbacks, and those
run on the engine's thread. Touching the UI from there would be unsafe. So the
listener below only *emits Qt signals*. Qt delivers a signal to an object that
lives in another thread by queueing it, which means the ``Backend`` slots always
run on the UI thread. That is the only crossing point between the two threads.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence

from PySide6.QtCore import Property, QObject, Signal, Slot

from streambridge.core.assembly import SetupError
from streambridge.core.engine import EngineListener, RelayEngine
from streambridge.core.events import ConnectionStatus
from streambridge.core.pipeline import Counters
from streambridge.ui.feed_model import FeedModel, FeedRow

logger = logging.getLogger(__name__)

SOURCE_ID = "source"
"""Id of the TikTok connection card. Destinations use their own name."""

EngineFactory = Callable[[EngineListener], RelayEngine]
"""Builds a fresh engine wired to the given listener. May raise ``SetupError``."""


class _QtListener(EngineListener):
    """Turns engine callbacks (engine thread) into Qt signals (safe for the UI)."""

    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def on_source_status(self, status: ConnectionStatus, detail: str) -> None:
        self._backend._status_in.emit(SOURCE_ID, str(status), detail)

    def on_destination_status(self, name: str, status: ConnectionStatus, detail: str) -> None:
        self._backend._status_in.emit(name, str(status), detail)

    def on_message_sent(self, destination: str, text: str) -> None:
        self._backend._message_in.emit(destination, text, "sent", "")

    def on_message_rejected(self, destination: str, text: str, reason: str) -> None:
        self._backend._message_in.emit(destination, text, "rejected", reason)

    def on_error(self, where: str, message: str) -> None:
        self._backend._error_in.emit(where, message)

    def on_counters(self, counters: Counters) -> None:
        self._backend._counters_in.emit(counters)

    def on_stopped(self) -> None:
        self._backend._stopped_in.emit()


class Backend(QObject):
    """Everything the dashboard needs: state, numbers, feed, and Start/Stop."""

    runningChanged = Signal()
    stoppingChanged = Signal()
    connectionsChanged = Signal()
    countersChanged = Signal()
    errorChanged = Signal()

    # Signals used only to hop from the engine thread to the UI thread.
    _status_in = Signal(str, str, str)
    _message_in = Signal(str, str, str, str)
    _error_in = Signal(str, str)
    _counters_in = Signal(object)
    _stopped_in = Signal()

    def __init__(
        self,
        engine_factory: EngineFactory,
        connection_ids: Sequence[str] = (SOURCE_ID,),
        parent: QObject | None = None,
    ) -> None:
        """Create the backend.

        Args:
            engine_factory: Builds a fresh engine for every Start.
            connection_ids: Ids of the status cards to show, in order. ``"source"``
                is TikTok; the others are destination names.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._engine_factory = engine_factory
        self._engine: RelayEngine | None = None
        self._running = False
        self._stopping = False
        self._error = ""
        self._feed = FeedModel(parent=self)
        self._connections: list[dict[str, str]] = [
            {"id": cid, "status": str(ConnectionStatus.STOPPED), "detail": ""}
            for cid in connection_ids
        ]
        self._sent = self._filtered = self._dropped = self._rejected = self._waiting = 0
        self._quota_used = self._quota_budget = 0  # a daily count: not reset per session

        self._status_in.connect(self._on_status)
        self._message_in.connect(self._on_message)
        self._error_in.connect(self._on_error)
        self._counters_in.connect(self._on_counters)
        self._stopped_in.connect(self._on_stopped)

    # --- Properties for QML -------------------------------------------------

    def _get_running(self) -> bool:
        return self._running

    def _get_stopping(self) -> bool:
        return self._stopping

    def _get_connections(self) -> list:
        return self._connections

    def _get_error(self) -> str:
        return self._error

    running = Property(bool, _get_running, notify=runningChanged)
    stopping = Property(bool, _get_stopping, notify=stoppingChanged)
    connections = Property(list, _get_connections, notify=connectionsChanged)
    lastError = Property(str, _get_error, notify=errorChanged)
    feed = Property(QObject, lambda self: self._feed, constant=True)  # type: ignore[arg-type]

    sentCount = Property(int, lambda self: self._sent, notify=countersChanged)
    filteredCount = Property(int, lambda self: self._filtered, notify=countersChanged)
    droppedCount = Property(int, lambda self: self._dropped, notify=countersChanged)
    rejectedCount = Property(int, lambda self: self._rejected, notify=countersChanged)
    waitingCount = Property(int, lambda self: self._waiting, notify=countersChanged)
    # quotaBudget is 0 until the engine reports a quota; the dashboard hides the counter then.
    quotaUsed = Property(int, lambda self: self._quota_used, notify=countersChanged)
    quotaBudget = Property(int, lambda self: self._quota_budget, notify=countersChanged)

    def set_connection_ids(self, connection_ids: Sequence[str]) -> None:
        """Change which status cards are shown. Ignored while the relay is running."""
        if self._running or self._stopping:
            return
        wanted = list(connection_ids)
        if wanted == [card["id"] for card in self._connections]:
            return
        self._connections = [
            {"id": cid, "status": str(ConnectionStatus.STOPPED), "detail": ""} for cid in wanted
        ]
        self.connectionsChanged.emit()
        if not any(cid.startswith("youtube") for cid in wanted) and self._quota_budget:
            self._quota_used = self._quota_budget = 0  # YouTube was removed: forget its quota
            self.countersChanged.emit()

    # --- Commands from QML --------------------------------------------------

    @Slot()
    def start(self) -> None:
        """Build a fresh engine and start relaying. Does nothing if already running."""
        if self._running or self._stopping:
            return
        self._set_error("")
        try:
            engine = self._engine_factory(_QtListener(self))
        except SetupError as problem:
            self._set_error("; ".join(problem.problems))
            return
        except Exception as problem:  # the UI must never crash on a setup mistake
            logger.exception("Could not build the engine")
            self._set_error(str(problem))
            return
        self._engine = engine
        self._feed.clear()
        self._reset_counters()
        for card in self._connections:
            card["status"] = str(ConnectionStatus.CONNECTING)
            card["detail"] = ""
        self.connectionsChanged.emit()
        self._set_running(True)
        engine.start()

    @Slot()
    def stop(self) -> None:
        """Ask the engine to stop. The wait happens off the UI thread."""
        engine = self._engine
        if engine is None or not self._running or self._stopping:
            return
        self._stopping = True
        self.stoppingChanged.emit()

        def run_stop() -> None:
            try:
                engine.stop()
            finally:
                self._stopped_in.emit()  # in case the engine never reported it

        threading.Thread(target=run_stop, name="EngineStop", daemon=True).start()

    # --- Slots that always run on the UI thread -----------------------------

    @Slot(str, str, str)
    def _on_status(self, connection_id: str, status: str, detail: str) -> None:
        for card in self._connections:
            if card["id"] == connection_id:
                card["status"], card["detail"] = status, detail
                break
        else:
            self._connections.append({"id": connection_id, "status": status, "detail": detail})
        self.connectionsChanged.emit()

    @Slot(str, str, str, str)
    def _on_message(self, destination: str, text: str, status: str, reason: str) -> None:
        self._feed.add(FeedRow(time.strftime("%H:%M:%S"), destination, text, status, reason))

    @Slot(str, str)
    def _on_error(self, where: str, message: str) -> None:
        self._set_error(f"{where}: {message}")

    @Slot(object)
    def _on_counters(self, counters: Counters) -> None:
        self._sent = sum(counters.sent.values())
        self._filtered = counters.filtered
        self._dropped = sum(counters.dropped.values())
        self._rejected = sum(counters.rejected.values())
        self._waiting = sum(counters.waiting.values())
        used, budget = self._read_quota(counters)
        if budget:  # a report without a quota (new session, still waiting) keeps the last one
            self._quota_used, self._quota_budget = used, budget
        self.countersChanged.emit()

    @staticmethod
    def _read_quota(counters: Counters) -> tuple[int, int]:
        """Return ``(used, budget)`` of the daily quota to show; ``(0, 0)`` means none.

        ``counters.quota_used`` is ``{destination: units}`` and ``counters.quota_budget``
        is one number. All YouTube routes share ONE tracker, so adding the values up
        would count the same units twice.
        """
        budget = counters.quota_budget
        if budget <= 0 or not counters.quota_used:
            return 0, 0
        return max(counters.quota_used.values()), budget  # max, not sum: one shared tracker

    @Slot()
    def _on_stopped(self) -> None:
        if not self._running and not self._stopping:
            return
        for card in self._connections:
            card["status"] = str(ConnectionStatus.STOPPED)
            card["detail"] = ""
        self.connectionsChanged.emit()
        self._engine = None
        if self._stopping:
            self._stopping = False
            self.stoppingChanged.emit()
        self._set_running(False)

    # --- Small helpers ------------------------------------------------------

    def _reset_counters(self) -> None:
        """Show zeros again, so numbers from the previous run do not linger."""
        self._sent = self._filtered = self._dropped = self._rejected = self._waiting = 0
        self.countersChanged.emit()

    def _set_running(self, value: bool) -> None:
        if self._running != value:
            self._running = value
            self.runningChanged.emit()

    def _set_error(self, message: str) -> None:
        if self._error != message:
            self._error = message
            self.errorChanged.emit()

    def shutdown(self) -> None:
        """Stop the engine and wait for it. Call this once, when the app is closing."""
        engine, self._engine = self._engine, None
        if engine is not None:
            engine.stop()
