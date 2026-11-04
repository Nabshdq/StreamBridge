"""YouTube compact mode: many chat messages joined into one.

Chat is collected for ``window`` seconds (counted from the first message of a
batch) and joined into one message no longer than ``max_length``::

    💬 TikTok: Budi: halo · Sari: nice

Chat that does not fit has two possible fates (``keep_newest``):

- ``False`` (default): it stays for the next batch.
- ``True``: the newest lines are sent, the rest of that window is dropped and
  counted. This is what YouTube uses, because its daily quota allows only a
  few messages and old chat is stale by the time a late batch goes out.

If too much chat piles up (more than ``max_pending``), the oldest is dropped
and counted, because YouTube cannot keep up anyway.
"""

from collections import deque

from streambridge.core.formatter import YOUTUBE_MAX_LENGTH, truncate

DEFAULT_COMPACT_WINDOW = 10.0
DEFAULT_SEPARATOR = " · "
DEFAULT_MAX_PENDING = 50


class ChatBatcher:
    """Collects chat lines and releases them as joined messages."""

    def __init__(
        self,
        prefix: str,
        window: float = DEFAULT_COMPACT_WINDOW,
        max_length: int = YOUTUBE_MAX_LENGTH,
        separator: str = DEFAULT_SEPARATOR,
        max_pending: int = DEFAULT_MAX_PENDING,
        keep_newest: bool = False,
    ) -> None:
        """Create a batcher.

        Args:
            prefix: Text at the start of every batch, e.g. ``"💬 TikTok:"``.
            window: Seconds to collect chat before sending.
            max_length: Maximum length of one joined message.
            separator: Text between two chat lines.
            max_pending: Most chat lines kept waiting; older ones are dropped.
            keep_newest: Send the newest lines and drop what does not fit,
                instead of carrying it to the next batch.
        """
        self.prefix = prefix
        self.window = window
        self.max_length = max_length
        self.separator = separator
        self.max_pending = max_pending
        self.keep_newest = keep_newest
        self.dropped_count = 0
        self.last_pop_dropped = 0  # lines dropped by the latest pop_due (keep_newest)
        self._lines: deque[str] = deque()
        self._batch_start: float | None = None

    def add(self, user: str, text: str, now: float) -> int:
        """Add one chat line. Returns how many old lines were dropped (0 or more)."""
        self._lines.append(f"{user}: {text}")
        if self._batch_start is None:
            self._batch_start = now
        dropped = 0
        while len(self._lines) > self.max_pending:
            self._lines.popleft()
            dropped += 1
        self.dropped_count += dropped
        return dropped

    def pop_due(self, now: float) -> list[str]:
        """Return one joined message if the window has ended, else an empty list."""
        if self._batch_start is None or now - self._batch_start < self.window:
            return []
        if self.keep_newest:
            message, dropped = self._pack_newest()
            self.dropped_count += dropped
            self.last_pop_dropped = dropped
        else:
            message = self._pack_one()
        self._batch_start = now if self._lines else None
        return [message]

    def discard_all(self) -> int:
        """Throw away all waiting chat. Returns how many lines were dropped."""
        count = len(self._lines)
        self._lines.clear()
        self._batch_start = None
        self.dropped_count += count
        return count

    def flush_all(self) -> list[str]:
        """Return all waiting chat as joined messages (used on stop)."""
        messages = []
        while self._lines:
            messages.append(self._pack_one())
        self._batch_start = None
        return messages

    def __len__(self) -> int:
        """Number of waiting chat lines."""
        return len(self._lines)

    def _pack_one(self) -> str:
        """Join as many waiting lines as fit into one message and remove them."""
        message = self.prefix
        packed = 0
        while self._lines:
            joiner = " " if packed == 0 else self.separator
            candidate = message + joiner + self._lines[0]
            if len(candidate) <= self.max_length:
                message = candidate
                self._lines.popleft()
                packed += 1
                continue
            if packed == 0:
                # A single line that is too long on its own: shorten it.
                message = truncate(candidate, self.max_length)
                self._lines.popleft()
            break
        return message

    def _pack_newest(self) -> tuple[str, int]:
        """Pack the newest lines that fit, drop the rest. Returns (message, dropped)."""
        lines = list(self._lines)
        self._lines.clear()
        chosen: list[str] = []
        length = len(self.prefix)
        for line in reversed(lines):
            extra = len(line) + (1 if not chosen else len(self.separator))
            if length + extra > self.max_length:
                break
            chosen.append(line)
            length += extra
        if not chosen:
            # The newest line alone is too long: shorten it.
            message = truncate(self.prefix + " " + lines[-1], self.max_length)
            return message, len(lines) - 1
        chosen.reverse()
        message = self.prefix + " " + self.separator.join(chosen)
        return message, len(lines) - len(chosen)
