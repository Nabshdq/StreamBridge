"""Abstract event source (where events come from)."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from streambridge.core.events import ConnectionStatus, RelayEvent

EmitEvent = Callable[[RelayEvent], None]
ReportStatus = Callable[[ConnectionStatus, str], None]


class Source(ABC):
    """Produces relay events, for example from a TikTok LIVE.

    The engine runs ``run`` as an asyncio task and cancels it to stop.
    """

    name: str = "source"

    @abstractmethod
    async def run(self, emit: EmitEvent, report_status: ReportStatus) -> None:
        """Produce events until cancelled.

        Args:
            emit: Call this with every new event.
            report_status: Call this when the connection state changes, with a
                short detail text (may be empty). Reporting ``CONNECTED`` starts
                a new session (for example, likes are counted again).
        """
