"""Abstract destination (where messages are sent)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from streambridge.core.ratelimit import RateRule


@dataclass(frozen=True)
class SendResult:
    """Outcome of sending one message.

    Attributes:
        ok: True if the platform accepted the message.
        reason: Why it was refused (for example Twitch's ``drop_reason``).
    """

    ok: bool
    reason: str = ""


class TemporarySendError(Exception):
    """Sending failed for a reason that may go away (network down, rate limited, 5xx).

    The engine waits and tries the same message again.
    """


class Destination(ABC):
    """A chat that receives relayed messages.

    Attributes:
        name: Short name shown in the UI and logs, e.g. ``"twitch"``.
        max_length: Longest message the platform accepts.
        rate_rules: Sending limits for this destination.
        max_queue_size: Queue limit; ``None`` means never drop messages.
    """

    name: str = "destination"
    max_length: int = 500
    rate_rules: tuple[RateRule, ...] = ()
    max_queue_size: int | None = None

    async def start(self) -> None:  # noqa: B027 - optional hook, empty by default
        """Prepare for sending (log in, find the chat). Raise if this is impossible."""

    @abstractmethod
    async def send(self, text: str) -> SendResult:
        """Send one message.

        Raises:
            TemporarySendError: If it should be retried later.
        """

    async def stop(self) -> None:  # noqa: B027 - optional hook, empty by default
        """Release resources (close connections)."""
