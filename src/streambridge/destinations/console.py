"""Destination that prints messages to the terminal (for development and tests)."""

import sys
import time
from collections.abc import Iterable
from typing import TextIO

from streambridge.core.ratelimit import RateRule
from streambridge.destinations.base import Destination, SendResult


class ConsoleDestination(Destination):
    """Prints every message with a time and the destination name."""

    def __init__(
        self,
        name: str = "console",
        max_length: int = 500,
        rate_rules: Iterable[RateRule] = (),
        max_queue_size: int | None = None,
        stream: TextIO | None = None,
    ) -> None:
        """Create a console destination.

        Args:
            name: Label printed before every message, e.g. ``"twitch-sim"``.
            max_length: Message length limit to simulate.
            rate_rules: Sending limits to simulate.
            max_queue_size: Queue limit to simulate (``None`` = never drop).
            stream: Where to print. Defaults to the current ``sys.stdout``.
        """
        self.name = name
        self.max_length = max_length
        self.rate_rules = tuple(rate_rules)
        self.max_queue_size = max_queue_size
        self._stream = stream

    async def send(self, text: str) -> SendResult:
        """Print the message."""
        stream = self._stream or sys.stdout
        line = f"{time.strftime('%H:%M:%S')} [{self.name}] {text}"
        # A Windows console (cp1252) cannot show emoji: print '?' instead of failing the send.
        encoding = getattr(stream, "encoding", None) or "utf-8"
        safe_line = line.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_line, file=stream, flush=True)
        return SendResult(ok=True)
