"""Tests for the local YouTube quota counter."""

from datetime import datetime

from streambridge.core.quota import (
    COST_INSERT,
    PACIFIC,
    QuotaTracker,
    is_gifts_only,
    pacific_date,
)


def at(year, month, day, hour, minute=0) -> float:
    """Epoch seconds for a Pacific wall-clock time."""
    return datetime(year, month, day, hour, minute, tzinfo=PACIFIC).timestamp()


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_records_and_reports(tmp_path):
    q = QuotaTracker(tmp_path / "q.json", clock=FakeClock(at(2026, 11, 4, 10)))
    q.record(COST_INSERT)
    q.record(COST_INSERT)
    assert q.used == 40
    assert q.remaining == 9960


def test_survives_restart_same_day(tmp_path):
    clock = FakeClock(at(2026, 11, 4, 10))
    QuotaTracker(tmp_path / "q.json", clock=clock).record(500)
    assert QuotaTracker(tmp_path / "q.json", clock=clock).used == 500


def test_resets_at_midnight_pacific_mid_session(tmp_path):
    clock = FakeClock(at(2026, 11, 4, 23, 59))
    q = QuotaTracker(tmp_path / "q.json", clock=clock)
    q.record(9000)
    assert q.gifts_only
    clock.now = at(2026, 11, 5, 0, 1)
    assert q.used == 0
    assert not q.gifts_only


def test_old_day_file_is_ignored_after_restart(tmp_path):
    QuotaTracker(tmp_path / "q.json", clock=FakeClock(at(2026, 11, 4, 12))).record(700)
    fresh = QuotaTracker(tmp_path / "q.json", clock=FakeClock(at(2026, 11, 5, 12)))
    assert fresh.used == 0


def test_gifts_only_at_ninety_percent(tmp_path):
    q = QuotaTracker(tmp_path / "q.json", clock=FakeClock(at(2026, 11, 4, 12)))
    q.record(8980)
    assert not q.gifts_only
    q.record(20)
    assert q.gifts_only


def test_broken_file_starts_from_zero(tmp_path):
    (tmp_path / "q.json").write_text("not json", encoding="utf-8")
    q = QuotaTracker(tmp_path / "q.json", clock=FakeClock(at(2026, 11, 4, 12)))
    assert q.used == 0


def test_pacific_date_follows_daylight_saving():
    # 2026-03-08 02:00 PT is when US clocks jump forward; the date logic must not break.
    assert pacific_date(at(2026, 3, 8, 12)) == "2026-03-08"
    assert pacific_date(at(2026, 3, 9, 0, 30)) == "2026-03-09"


def test_is_gifts_only_boundary():
    assert not is_gifts_only(8_999, 10_000)
    assert is_gifts_only(9_000, 10_000)
    assert is_gifts_only(10_000, 10_000)
    assert not is_gifts_only(0, 0)  # no budget known: never gifts-only
