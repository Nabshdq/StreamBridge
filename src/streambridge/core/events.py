"""Standard event model shared by every source, filter and destination."""

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

EventKind = Literal["chat", "gift", "follow", "like", "share", "repost"]

EVENT_KINDS: tuple[EventKind, ...] = ("chat", "gift", "follow", "like", "share", "repost")

PRIORITY_HIGH = 0
PRIORITY_LOW = 1

# These kinds are sent before chat and are never dropped from a full queue.
HIGH_PRIORITY_KINDS: frozenset[str] = frozenset({"gift", "follow", "share", "repost"})


class ConnectionStatus(StrEnum):
    """Connection state of a source or destination, shown in the UI."""

    WAITING_LIVE = "waiting_live"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    STOPPED = "stopped"


def priority_for(kind: str) -> int:
    """Return the queue priority for an event kind (lower = sent sooner)."""
    return PRIORITY_HIGH if kind in HIGH_PRIORITY_KINDS else PRIORITY_LOW


@dataclass(frozen=True)
class RelayEvent:
    """One thing that happened on the source LIVE (a chat, gift, follow, ...).

    Attributes:
        kind: What happened.
        platform: Where it happened, e.g. ``"tiktok"``.
        user: Cleaned display name of the viewer.
        text: Chat text (only for ``chat``).
        gift_name: Name of the gift (only for ``gift``).
        gift_count: How many gifts (only for ``gift``).
        user_id: Stable viewer id, used to recognise the same viewer. Optional.
        timestamp: When the event happened (seconds since the epoch).
    """

    kind: EventKind
    platform: str
    user: str
    text: str = ""
    gift_name: str = ""
    gift_count: int = 1
    user_id: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def priority(self) -> int:
        """Gifts, follows, shares and reposts go before chat and likes (lower = sooner)."""
        return priority_for(self.kind)

    @property
    def user_key(self) -> str:
        """Key that identifies the viewer: the id if known, else the lower-cased name."""
        return self.user_id or self.user.casefold()
