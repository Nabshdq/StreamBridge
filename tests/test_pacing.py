"""Tests for the quota-aware compact window."""

import pytest

from streambridge.core.pacing import (
    DEFAULT_RESERVE,
    MAX_WINDOW,
    MIN_WINDOW,
    OVERRUN_HORIZON,
    compact_window,
)

THREE_HOURS = 3 * 3600.0


def test_default_reserve_matches_the_gifts_only_switch():
    assert DEFAULT_RESERVE == 50


def test_three_hours_with_400_usable_sends():
    assert compact_window(450, THREE_HOURS, sends_reserved=50) == pytest.approx(27.0)


def test_large_budget_clamps_to_minimum():
    assert compact_window(100_000, 600.0) == MIN_WINDOW


def test_tiny_budget_clamps_to_maximum():
    assert compact_window(DEFAULT_RESERVE + 1, THREE_HOURS) == MAX_WINDOW


@pytest.mark.parametrize("sends_left", [0, DEFAULT_RESERVE, DEFAULT_RESERVE - 10])
def test_no_chat_budget_uses_the_slowest_pace(sends_left):
    assert compact_window(sends_left, THREE_HOURS) == MAX_WINDOW


def test_past_the_target_keeps_pacing_instead_of_sprinting():
    usable = 60
    window = compact_window(DEFAULT_RESERVE + usable, -500.0)
    assert window == pytest.approx(OVERRUN_HORIZON / usable)


def test_quota_reset_shortens_the_window():
    before = compact_window(DEFAULT_RESERVE + 100, 7200.0)
    after = compact_window(500, 7200.0)
    assert after < before
