"""Local counter for the daily YouTube API quota.

Google gives every project 10,000 units per day and resets the count at
midnight Pacific Time. Each API call costs some units. We cannot ask Google
how much is left cheaply, so we count our own calls and keep the number in a
small state file. Saving it matters: without it, restarting the app halfway
through the day would reset the count to zero and we would overspend.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")
DAILY_BUDGET = 10_000
GIFTS_ONLY_FRACTION = 0.9

# Units per call (YouTube docs, checked 2026-11-04).
COST_INSERT = 20  # liveChatMessages.insert (send one message)
COST_LIST_CHAT = 5  # liveChatMessages.list
COST_VIDEOS_LIST = 1  # videos.list
COST_BROADCASTS_LIST = 1  # liveBroadcasts.list


def is_gifts_only(used: int, budget: int) -> bool:
    """True once ``used`` reaches 90% of ``budget``: only gifts and follows should be sent.

    The pipeline and the dashboard both ask this, so they agree at the exact boundary.
    """
    return budget > 0 and used / budget >= GIFTS_ONLY_FRACTION


_shared: dict[Path, "QuotaTracker"] = {}


def shared_quota(path: Path) -> "QuotaTracker":
    """One tracker per file, so the destination and the dashboard count the same units."""
    if path not in _shared:
        _shared[path] = QuotaTracker(path)
    return _shared[path]


def pacific_date(timestamp: float) -> str:
    """Return the Pacific-time calendar date of ``timestamp`` as ``YYYY-MM-DD``."""
    return datetime.fromtimestamp(timestamp, PACIFIC).date().isoformat()


class QuotaTracker:
    """Count quota units used today (Pacific date) and survive restarts."""

    def __init__(
        self,
        path: Path,
        budget: int = DAILY_BUDGET,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = path
        self.budget = budget
        self._clock = clock
        self._date = pacific_date(clock())
        self._used = 0
        self._load()

    @property
    def used(self) -> int:
        """Units used so far today (rolls over at midnight Pacific)."""
        self._roll_over()
        return self._used

    @property
    def remaining(self) -> int:
        """Units left today, never below zero."""
        return max(0, self.budget - self.used)

    @property
    def fraction(self) -> float:
        """Share of today's budget already used (0.0 to 1.0 and above)."""
        return self.used / self.budget

    @property
    def gifts_only(self) -> bool:
        """True once usage reaches 90%: only gifts and follows should be sent."""
        return is_gifts_only(self.used, self.budget)

    def record(self, cost: int) -> None:
        """Add ``cost`` units for one API call and save the new total."""
        self._roll_over()
        self._used += cost
        self._save()

    def _roll_over(self) -> None:
        """Start a fresh budget when the Pacific date has changed."""
        today = pacific_date(self._clock())
        if today != self._date:
            logger.info("YouTube quota reset for %s", today)
            self._date = today
            self._used = 0
            self._save()

    def _load(self) -> None:
        """Read the saved count; ignore it if it is from an earlier day or broken."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if data.get("date") == self._date:
                self._used = max(0, int(data.get("used", 0)))
        except (OSError, ValueError, TypeError):
            pass

    def _save(self) -> None:
        """Write the count to disk; a failure is logged, never fatal."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"date": self._date, "used": self._used}
            self._path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            logger.warning("Could not save the YouTube quota file", exc_info=True)
