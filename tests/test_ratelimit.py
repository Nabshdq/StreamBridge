"""Tests for the sliding-window rate limiter."""

import asyncio

import pytest

from streambridge.core.ratelimit import SAFETY_MARGIN, TWITCH_RULES, RateLimiter, RateRule


class FakeClock:
    """A clock that only moves when the test says so."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def send_all_possible(limiter: RateLimiter, clock: FakeClock) -> int:
    """Send as many messages as allowed right now; return how many."""
    sent = 0
    while limiter.wait_time() <= 0:
        limiter.record()
        sent += 1
    return sent


def test_twitch_allows_80_then_waits() -> None:
    """80 messages go out at once; the 81st must wait for the window."""
    clock = FakeClock()
    limiter = RateLimiter(TWITCH_RULES, clock=clock)
    assert send_all_possible(limiter, clock) == 80
    assert limiter.wait_time() == pytest.approx(30.0 + SAFETY_MARGIN)


def test_never_more_than_80_in_any_30_seconds() -> None:
    """Simulate 10 minutes of sending as fast as allowed and check every window."""
    clock = FakeClock()
    limiter = RateLimiter(TWITCH_RULES, clock=clock)
    sent_times: list[float] = []
    while clock.now < 600:
        wait = limiter.wait_time()
        if wait > 0:
            clock.now += wait
            continue
        limiter.record()
        sent_times.append(clock.now)
        clock.now += 0.05  # a fast sender
    for index, start in enumerate(sent_times):
        in_window = [t for t in sent_times[index:] if t - start < 30.0]
        assert len(in_window) <= 80


def test_sliding_window_frees_slots_gradually() -> None:
    """Slots come back as old messages leave the window."""
    clock = FakeClock()
    limiter = RateLimiter([RateRule(2, 10.0)], clock=clock)
    limiter.record()  # t=0
    clock.now = 4.0
    limiter.record()  # t=4
    assert limiter.wait_time() == pytest.approx(6.0 + SAFETY_MARGIN)
    clock.now = 10.0 + SAFETY_MARGIN
    assert limiter.wait_time() == 0
    limiter.record()
    assert limiter.wait_time() == pytest.approx(4.0)


def test_all_rules_must_hold() -> None:
    """With two rules, the stricter one at that moment decides."""
    clock = FakeClock()
    limiter = RateLimiter([RateRule(1, 1.0), RateRule(3, 30.0)], clock=clock)
    step = 1.0 + SAFETY_MARGIN  # just long enough for the 1-per-second rule
    for _ in range(3):
        assert limiter.wait_time() == 0
        limiter.record()
        clock.now += step
    # Now the 3-per-30-seconds rule blocks until the first message leaves its window.
    assert limiter.wait_time() == pytest.approx(30.0 + SAFETY_MARGIN - 3 * step)


async def test_acquire_waits_for_a_free_slot() -> None:
    """acquire() sleeps until sending is allowed."""
    limiter = RateLimiter([RateRule(1, 0.05)])
    loop = asyncio.get_running_loop()
    start = loop.time()
    await limiter.acquire()
    await limiter.acquire()
    assert loop.time() - start >= 0.04


def test_youtube_rules_stay_within_help_center_limit():
    """YouTube must never exceed 11 messages in any 30 s window."""
    from streambridge.core.ratelimit import YOUTUBE_RULES

    assert (RateRule(11, 30.0),) == YOUTUBE_RULES
