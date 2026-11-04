"""Quota-aware pacing for the YouTube compact-chat window.

YouTube allows 10,000 quota units a day and one message costs 20, so at most
500 messages a day. A fixed 10 s window would use that up in about 1.4 hours.
This module decides how long the compact window should be so the quota lasts
for the whole LIVE.
"""

from streambridge.core.quota import COST_INSERT, DAILY_BUDGET, GIFTS_ONLY_FRACTION

DEFAULT_LIVE_TARGET = 3 * 3600.0
"""Planned LIVE length in seconds (a setting comes with the Settings page)."""

MIN_WINDOW = 20.0
"""Never batch faster than this many seconds (also protects the send limit)."""

MAX_WINDOW = 120.0
"""Never wait longer than this: chat would feel too late."""

OVERRUN_HORIZON = 1800.0
"""When the LIVE runs past its target, keep pacing over this many seconds."""

DEFAULT_RESERVE = round(DAILY_BUDGET * (1 - GIFTS_ONLY_FRACTION)) // COST_INSERT
"""Sends kept for gifts: what is left when the 90% gifts-only switch starts."""


def compact_window(
    sends_left: int,
    seconds_left: float,
    sends_reserved: int = DEFAULT_RESERVE,
) -> float:
    """Return the compact-chat window in seconds.

    Args:
        sends_left: Messages the remaining quota can still pay for
            (remaining units // 20).
        seconds_left: Seconds until the planned end of the LIVE
            (for example a 3 hour target minus the time already streamed).
        sends_reserved: Messages kept back for gifts, which are sent on
            their own and must never be starved by chat batching.

    Returns:
        A window between ``MIN_WINDOW`` and ``MAX_WINDOW`` seconds.
    """
    usable = sends_left - sends_reserved
    if usable <= 0:
        return MAX_WINDOW  # chat budget gone: slowest pace, gifts still go out alone
    horizon = max(seconds_left, OVERRUN_HORIZON)  # past the target: keep pacing, don't sprint
    return min(MAX_WINDOW, max(MIN_WINDOW, horizon / usable))
