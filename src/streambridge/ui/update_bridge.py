"""Qt side of the "new version available" notice.

The check itself (``core/updates.py``) is plain Python. This object runs it once, on a
background thread so the window never waits for the network, and hands the answer back
to the UI thread through a signal. QML only reads ``available``, ``latestVersion`` and
``releaseUrl``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import Property, QObject, Signal, Slot

from streambridge.core.updates import UpdateInfo

logger = logging.getLogger(__name__)

UpdateChecker = Callable[[], UpdateInfo | None]


class UpdateBridge(QObject):
    """Runs the update check once and exposes the result to QML."""

    changed = Signal()
    # Emitted from the worker thread; Qt delivers it on the UI thread (queued connection).
    _result_ready = Signal(object)

    def __init__(self, checker: UpdateChecker | None = None, parent: QObject | None = None):
        """``checker`` returns the newer release or None; None means "never check" (tests)."""
        super().__init__(parent)
        self._checker = checker
        self._update: UpdateInfo | None = None
        self._started = False
        self._result_ready.connect(self._on_result)

    @Property(bool, notify=changed)
    def available(self) -> bool:
        """True when a newer release exists."""
        return self._update is not None

    @Property(str, notify=changed)
    def latestVersion(self) -> str:
        """The newer version, for example ``0.2.0`` (empty when there is none)."""
        return self._update.version if self._update else ""

    @Property(str, notify=changed)
    def releaseUrl(self) -> str:
        """The release page to open in the browser (empty when there is none)."""
        return self._update.url if self._update else ""

    def start(self) -> None:
        """Begin the check in the background. Calling it twice does nothing."""
        if self._checker is None or self._started:
            return
        self._started = True
        threading.Thread(target=self._worker, name="UpdateCheck", daemon=True).start()

    def _worker(self) -> None:
        """Runs on the background thread: ask, then hand the answer to the UI thread."""
        assert self._checker is not None
        try:
            update = self._checker()
        except Exception:  # the check is a courtesy; it must never become a crash report
            logger.info("Update check failed unexpectedly", exc_info=True)
            update = None
        try:
            self._result_ready.emit(update)
        except RuntimeError:
            # The window was closed (this object deleted) while the request was running.
            logger.debug("Update check finished after the window closed")

    @Slot(object)
    def _on_result(self, update: UpdateInfo | None) -> None:
        """Runs on the UI thread."""
        if update != self._update:
            self._update = update
            self.changed.emit()
