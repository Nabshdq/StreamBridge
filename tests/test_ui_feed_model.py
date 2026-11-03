"""Tests for the dashboard feed model."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QModelIndex  # noqa: E402

from streambridge.ui.feed_model import FeedModel, FeedRole, FeedRow  # noqa: E402


def make_row(number: int, **overrides) -> FeedRow:
    """Build a sent row whose text identifies it."""
    values = {"time_text": "12:00:00", "destination": "twitch", "text": f"message {number}"}
    values.update(overrides)
    return FeedRow(**values)


def test_starts_empty():
    model = FeedModel()
    assert model.rowCount() == 0
    assert model.count == 0


def test_add_appends_newest_last():
    model = FeedModel()
    model.add(make_row(1))
    model.add(make_row(2))
    assert model.rowCount() == 2
    assert model.data(model.index(0), FeedRole.TEXT) == "message 1"
    assert model.data(model.index(1), FeedRole.TEXT) == "message 2"


def test_exposes_every_role_to_qml():
    model = FeedModel()
    model.add(make_row(1, status="rejected", reason="too long"))
    index = model.index(0)
    assert model.data(index, FeedRole.TIME) == "12:00:00"
    assert model.data(index, FeedRole.DESTINATION) == "twitch"
    assert model.data(index, FeedRole.STATUS) == "rejected"
    assert model.data(index, FeedRole.REASON) == "too long"
    names = {bytes(name).decode() for name in model.roleNames().values()}
    assert names == {"time", "destination", "text", "status", "reason"}


def test_keeps_only_the_newest_rows():
    model = FeedModel(max_rows=3)
    for number in range(1, 6):
        model.add(make_row(number))
    assert model.rowCount() == 3
    assert [model.row_at(i).text for i in range(3)] == ["message 3", "message 4", "message 5"]


def test_a_flood_of_messages_stays_bounded():
    model = FeedModel(max_rows=200)
    for number in range(5000):
        model.add(make_row(number))
    assert model.rowCount() == 200
    assert model.row_at(199).text == "message 4999"


def test_clear_empties_the_feed():
    model = FeedModel()
    model.add(make_row(1))
    model.clear()
    assert model.rowCount() == 0
    assert model.count == 0


def test_count_changed_is_emitted():
    model = FeedModel()
    seen: list[int] = []
    model.countChanged.connect(lambda: seen.append(model.count))
    model.add(make_row(1))
    model.add(make_row(2))
    model.clear()
    assert seen == [1, 2, 0]


def test_invalid_index_returns_nothing():
    model = FeedModel()
    assert model.data(QModelIndex(), FeedRole.TEXT) is None
    assert model.data(model.index(7), FeedRole.TEXT) is None


def test_rows_are_removed_with_proper_notifications():
    model = FeedModel(max_rows=2)
    removed: list[tuple[int, int]] = []
    model.rowsRemoved.connect(lambda _parent, first, last: removed.append((first, last)))
    for number in range(3):
        model.add(make_row(number))
    assert removed == [(0, 0)]
