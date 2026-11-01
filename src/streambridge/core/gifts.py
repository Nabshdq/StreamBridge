"""Gift combo merger.

Gifts with the same viewer and gift name that arrive within ``delay`` seconds
of the **first** one are summed into one event (fixed window). Example with
``delay=5``: Rose at 0 s and 3 s -> "Rose x2" released at 5 s; a Rose at 6 s
starts a new window.

On stop, call ``flush_all()`` so buffered gifts are sent, not lost.
"""

from dataclasses import dataclass, replace

from streambridge.core.events import RelayEvent

DEFAULT_GIFT_DELAY = 5.0


@dataclass
class _PendingGift:
    """Gifts collected in one open window."""

    first_event: RelayEvent
    total_count: int
    window_start: float


class GiftMerger:
    """Collects gifts for a short time and releases them as merged events."""

    def __init__(self, delay: float = DEFAULT_GIFT_DELAY) -> None:
        """Create the merger. ``delay`` is the window length in seconds."""
        self.delay = delay
        self._pending: dict[tuple[str, str], _PendingGift] = {}

    def add(self, event: RelayEvent, now: float) -> None:
        """Add a gift event. ``now`` is the current time in seconds."""
        key = (event.user_key, event.gift_name.casefold())
        pending = self._pending.get(key)
        if pending is None:
            self._pending[key] = _PendingGift(event, event.gift_count, now)
        else:
            pending.total_count += event.gift_count

    def pop_due(self, now: float) -> list[RelayEvent]:
        """Return merged gifts whose window has ended, oldest first."""
        due_keys = [
            key
            for key, pending in self._pending.items()
            if now - pending.window_start >= self.delay
        ]
        return [self._release(key) for key in due_keys]

    def flush_all(self) -> list[RelayEvent]:
        """Return every buffered gift now, regardless of its window."""
        return [self._release(key) for key in list(self._pending)]

    def __len__(self) -> int:
        """Number of open gift windows."""
        return len(self._pending)

    def _release(self, key: tuple[str, str]) -> RelayEvent:
        """Remove one window and return its merged event."""
        pending = self._pending.pop(key)
        return replace(pending.first_event, gift_count=pending.total_count)
