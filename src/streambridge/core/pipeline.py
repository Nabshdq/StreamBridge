"""The relay pipeline: filter -> de-duplicate -> merge gifts -> route -> queue.

Per destination ("route"): event toggle -> compact batch (YouTube chat only)
-> format -> outgoing queue. Sending from the queues is done by the engine.

All methods must be called from the engine's event loop thread.
"""

import copy
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from streambridge.core.batching import ChatBatcher
from streambridge.core.events import PRIORITY_HIGH, RelayEvent
from streambridge.core.filters import MessageFilter
from streambridge.core.formatter import MessageFormatter, truncate
from streambridge.core.gifts import GiftMerger
from streambridge.core.likes import SocialDeduper
from streambridge.core.outqueue import OutMessage, OutQueue

logger = logging.getLogger(__name__)


@dataclass
class Counters:
    """Numbers shown on the dashboard.

    Attributes:
        sent: Messages accepted by each destination.
        filtered: Chat messages dropped by the spam filter.
        dropped: Messages dropped by each destination because it could not keep up.
        rejected: Messages refused by each destination (e.g. Twitch AutoMod).
        waiting: Messages waiting in each destination's queue.
        unsent_on_stop: Messages still waiting when the relay was stopped.
    """

    sent: dict[str, int] = field(default_factory=dict)
    filtered: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    rejected: dict[str, int] = field(default_factory=dict)
    waiting: dict[str, int] = field(default_factory=dict)
    unsent_on_stop: int = 0

    def add_destination(self, name: str) -> None:
        """Start counting for a destination."""
        for counter in (self.sent, self.dropped, self.rejected, self.waiting):
            counter.setdefault(name, 0)

    def snapshot(self) -> "Counters":
        """Return an independent copy (safe to hand to another thread)."""
        return copy.deepcopy(self)


@dataclass
class Route:
    """Everything the pipeline needs to know about one destination.

    Attributes:
        name: Destination name.
        toggles: ``{kind: enabled}`` event toggles.
        formatter: Formats single events for this destination.
        queue: The destination's outgoing queue.
        batcher: Compact-mode batcher for chat, or ``None``.
    """

    name: str
    toggles: Mapping[str, bool]
    formatter: MessageFormatter
    queue: OutQueue
    batcher: ChatBatcher | None = None

    def wants(self, kind: str) -> bool:
        """True if this destination receives events of ``kind``."""
        return self.toggles.get(kind, False)


class Pipeline:
    """Turns incoming events into queued messages for every destination."""

    def __init__(
        self,
        message_filter: MessageFilter,
        deduper: SocialDeduper,
        gift_merger: GiftMerger,
        routes: Iterable[Route],
        counters: Counters | None = None,
    ) -> None:
        """Create the pipeline from its parts."""
        self.message_filter = message_filter
        self.deduper = deduper
        self.gift_merger = gift_merger
        self.routes = list(routes)
        self.counters = counters or Counters()
        for route in self.routes:
            self.counters.add_destination(route.name)

    def handle(self, event: RelayEvent, now: float) -> None:
        """Process one incoming event."""
        result = self.message_filter.check(event)
        if result.event is None:
            self.counters.filtered += 1
            logger.debug("Filtered (%s): %s", result.reason, event)
            return
        event = result.event
        if not self.deduper.allow(event):
            return
        if event.kind == "gift":
            self.gift_merger.add(event, now)
            return
        self._route(event, now)

    def tick(self, now: float) -> None:
        """Release merged gifts and compact batches whose time has come."""
        for gift in self.gift_merger.pop_due(now):
            self._route(gift, now)
        for route in self.routes:
            if route.batcher is not None:
                for text in route.batcher.pop_due(now):
                    self._deliver(route, OutMessage.for_kind(text, "chat"))

    def flush_all(self, now: float) -> None:
        """Release everything that is being held back (used on stop)."""
        for gift in self.gift_merger.flush_all():
            self._route(gift, now)
        for route in self.routes:
            self.flush_batcher(route)

    def flush_batcher(self, route: Route) -> None:
        """Queue all chat a route's compact batcher is holding (nothing is lost)."""
        if route.batcher is not None:
            for text in route.batcher.flush_all():
                self._deliver(route, OutMessage.for_kind(text, "chat"))

    def reset_session(self) -> None:
        """Start a new session (the TikTok LIVE connected again)."""
        self.deduper.reset()

    def enqueue_text(self, text: str) -> None:
        """Queue a plain text (e.g. a test message) for every destination, sent first."""
        for route in self.routes:
            message = OutMessage(truncate(text, route.formatter.max_length), "test", PRIORITY_HIGH)
            self._deliver(route, message)

    def _route(self, event: RelayEvent, now: float) -> None:
        """Send an event to every destination that wants it."""
        for route in self.routes:
            if not route.wants(event.kind):
                continue
            if event.kind == "chat" and route.batcher is not None:
                dropped = route.batcher.add(event.user, event.text, now)
                self.counters.dropped[route.name] += dropped
                continue
            text = route.formatter.format(event)
            self._deliver(route, OutMessage.for_kind(text, event.kind))

    def _deliver(self, route: Route, message: OutMessage) -> None:
        """Put a message in a destination's queue and count any drop."""
        dropped = route.queue.put(message)
        if dropped is not None:
            self.counters.dropped[route.name] += 1
            logger.info("Queue full for %s; dropped: %s", route.name, dropped.text)
