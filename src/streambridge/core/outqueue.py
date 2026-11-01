"""Per-destination outgoing queue with priorities.

- High priority (gifts, follows, shares, reposts, test messages) leaves first.
- Within one priority, messages leave in arrival order.
- ``max_size=None`` (Twitch): nothing is ever dropped.
- ``max_size=30`` (YouTube): when full, the **oldest chat or like** is dropped.
  High-priority messages are never dropped.

All methods must be called from the engine's event loop thread.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from streambridge.core.events import PRIORITY_HIGH, priority_for

YOUTUBE_MAX_QUEUE = 30


@dataclass(frozen=True)
class OutMessage:
    """A finished message waiting to be sent to one destination."""

    text: str
    kind: str
    priority: int
    created_at: float = field(default_factory=time.time)

    @classmethod
    def for_kind(cls, text: str, kind: str) -> "OutMessage":
        """Create a message with the standard priority for ``kind``."""
        return cls(text=text, kind=kind, priority=priority_for(kind))


class OutQueue:
    """Priority queue that can drop old low-priority messages when full."""

    def __init__(self, max_size: int | None = None) -> None:
        """Create a queue. ``max_size=None`` means unlimited (never drop)."""
        self.max_size = max_size
        self.dropped_count = 0
        self._high: deque[OutMessage] = deque()
        self._low: deque[OutMessage] = deque()
        self._has_items = asyncio.Event()

    def put(self, message: OutMessage) -> OutMessage | None:
        """Add a message. Returns the message that was dropped to make room, if any."""
        target = self._high if message.priority == PRIORITY_HIGH else self._low
        target.append(message)
        self._has_items.set()

        if self.max_size is None or len(self) <= self.max_size or not self._low:
            return None
        self.dropped_count += 1
        return self._low.popleft()

    def get_nowait(self) -> OutMessage | None:
        """Take the next message, or ``None`` if the queue is empty."""
        if self._high:
            message = self._high.popleft()
        elif self._low:
            message = self._low.popleft()
        else:
            return None
        if not self:
            self._has_items.clear()
        return message

    async def get(self) -> OutMessage:
        """Wait for and take the next message."""
        while True:
            message = self.get_nowait()
            if message is not None:
                return message
            await self._has_items.wait()

    @property
    def high_priority_count(self) -> int:
        """Number of waiting high-priority messages."""
        return len(self._high)

    def __len__(self) -> int:
        """Number of waiting messages."""
        return len(self._high) + len(self._low)
