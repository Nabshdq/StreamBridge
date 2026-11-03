"""List model behind the live message feed on the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
)

MAX_FEED_ROWS = 200
"""The feed keeps only this many of the newest rows, so memory stays small."""

Index = QModelIndex | QPersistentModelIndex


@dataclass(frozen=True)
class FeedRow:
    """One line in the feed.

    Attributes:
        time_text: Wall-clock time already formatted for display, e.g. "14:03:07".
        destination: Name of the destination, e.g. "twitch".
        text: The message that was relayed (or refused).
        status: "sent" for a delivered message, "rejected" for one the platform refused.
        reason: Why it was refused. Empty for sent messages.
    """

    time_text: str
    destination: str
    text: str
    status: str = "sent"
    reason: str = ""


class FeedRole(IntEnum):
    """Role numbers QML uses to read each part of a row."""

    TIME = Qt.ItemDataRole.UserRole + 1
    DESTINATION = Qt.ItemDataRole.UserRole + 2
    TEXT = Qt.ItemDataRole.UserRole + 3
    STATUS = Qt.ItemDataRole.UserRole + 4
    REASON = Qt.ItemDataRole.UserRole + 5


class FeedModel(QAbstractListModel):
    """Newest-last list of relayed messages, capped at ``max_rows``."""

    countChanged = Signal()

    def __init__(self, max_rows: int = MAX_FEED_ROWS, parent=None) -> None:
        """Create an empty feed.

        Args:
            max_rows: How many rows to keep; older rows are removed first.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._max_rows = max(1, max_rows)
        self._rows: list[FeedRow] = []

    # --- Qt model interface -------------------------------------------------

    def rowCount(self, parent: Index = QModelIndex()) -> int:  # noqa: B008
        """Return the number of rows (a flat list has none under a parent)."""
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return one part of a row for QML."""
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == FeedRole.TIME:
            return row.time_text
        if role == FeedRole.DESTINATION:
            return row.destination
        if role in (FeedRole.TEXT, Qt.ItemDataRole.DisplayRole):
            return row.text
        if role == FeedRole.STATUS:
            return row.status
        if role == FeedRole.REASON:
            return row.reason
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        """Names QML uses: ``time``, ``destination``, ``text``, ``status``, ``reason``."""
        return {
            FeedRole.TIME: QByteArray(b"time"),
            FeedRole.DESTINATION: QByteArray(b"destination"),
            FeedRole.TEXT: QByteArray(b"text"),
            FeedRole.STATUS: QByteArray(b"status"),
            FeedRole.REASON: QByteArray(b"reason"),
        }

    # --- Our own API --------------------------------------------------------

    def _get_count(self) -> int:
        return len(self._rows)

    count = Property(int, _get_count, notify=countChanged)  # type: ignore[assignment]

    def add(self, row: FeedRow) -> None:
        """Append a row at the end and drop the oldest rows beyond the limit."""
        position = len(self._rows)
        self.beginInsertRows(QModelIndex(), position, position)
        self._rows.append(row)
        self.endInsertRows()

        excess = len(self._rows) - self._max_rows
        if excess > 0:
            self.beginRemoveRows(QModelIndex(), 0, excess - 1)
            del self._rows[:excess]
            self.endRemoveRows()
        self.countChanged.emit()

    def clear(self) -> None:
        """Remove every row."""
        if not self._rows:
            return
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()
        self.countChanged.emit()

    def row_at(self, position: int) -> FeedRow:
        """Return the row at ``position`` (for tests and the bridge)."""
        return self._rows[position]
