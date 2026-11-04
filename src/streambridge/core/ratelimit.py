"""Sliding-window rate limiter.

A rule such as "80 messages per 30 seconds" is enforced over **any** 30-second
span, not only fixed blocks. The limiter remembers when recent messages were
sent and waits until the oldest one is outside the window.
"""

import asyncio
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

Clock = Callable[[], float]

# Extra seconds added to every window, so rounding errors and network jitter
# can never push us over the platform's limit.
SAFETY_MARGIN = 0.05


@dataclass(frozen=True)
class RateRule:
    """At most ``max_messages`` within any ``per_seconds`` span."""

    max_messages: int
    per_seconds: float


# Twitch: broadcaster or moderator sender (a separate bot must be a moderator).
TWITCH_RULES: tuple[RateRule, ...] = (RateRule(80, 30.0),)

# YouTube: the API send rate is not documented. The Help Center allows chat users
# 11 messages per 30 s, so we stay at that. The daily quota (core/quota.py) is the
# stricter limit in practice.
YOUTUBE_RULES: tuple[RateRule, ...] = (RateRule(11, 30.0),)


class RateLimiter:
    """Waits as long as needed so that every rule is respected."""

    def __init__(self, rules: Iterable[RateRule], clock: Clock = time.monotonic) -> None:
        """Create a limiter.

        Args:
            rules: All rules that must hold at the same time.
            clock: Returns the current time in seconds (replaceable in tests).
        """
        self.rules = tuple(rules)
        self._clock = clock
        self._history: list[deque[float]] = [deque() for _ in self.rules]

    def wait_time(self, now: float | None = None) -> float:
        """Seconds to wait before the next message may be sent (0 = send now)."""
        now = self._clock() if now is None else now
        longest = 0.0
        for rule, sent_times in zip(self.rules, self._history, strict=True):
            self._forget_old(rule, sent_times, now)
            if len(sent_times) >= rule.max_messages:
                window = rule.per_seconds + SAFETY_MARGIN
                longest = max(longest, sent_times[0] + window - now)
        return longest

    def record(self, now: float | None = None) -> None:
        """Remember that a message was sent now."""
        now = self._clock() if now is None else now
        for sent_times in self._history:
            sent_times.append(now)

    async def acquire(self) -> None:
        """Wait until a message may be sent, then record it."""
        while True:
            wait = self.wait_time()
            if wait <= 0:
                self.record()
                return
            await asyncio.sleep(wait)

    @staticmethod
    def _forget_old(rule: RateRule, sent_times: deque[float], now: float) -> None:
        """Drop send times that are outside the rule's window (plus safety margin)."""
        while sent_times and now - sent_times[0] >= rule.per_seconds + SAFETY_MARGIN:
            sent_times.popleft()
