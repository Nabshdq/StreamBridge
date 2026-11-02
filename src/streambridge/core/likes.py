"""Keeps likes, shares and reposts from flooding the destinations.

- Like: only a viewer's **first** like in a session is relayed.
- Share / repost: the same viewer again within ``repeat_window`` seconds is ignored.

A session starts when the relay starts or the TikTok LIVE (re)connects; call
``reset()`` then. Both memories are bounded so they never grow without limit.
"""

from collections import OrderedDict

from streambridge.core.events import RelayEvent

DEFAULT_SHARE_REPEAT_WINDOW = 60.0
MAX_REMEMBERED_VIEWERS = 50_000


class SocialDeduper:
    """Decides whether a like, share or repost should be relayed."""

    def __init__(
        self,
        repeat_window: float = DEFAULT_SHARE_REPEAT_WINDOW,
        max_viewers: int = MAX_REMEMBERED_VIEWERS,
    ) -> None:
        """Create the deduper.

        Args:
            repeat_window: Seconds in which a repeated share/repost is ignored.
            max_viewers: Upper bound for each memory; the oldest entries are forgotten.
        """
        self.repeat_window = repeat_window
        self._max_viewers = max_viewers
        self._liked: OrderedDict[str, None] = OrderedDict()
        # (kind, viewer) -> last time a share/repost was relayed.
        self._last_shared: OrderedDict[tuple[str, str], float] = OrderedDict()

    def allow(self, event: RelayEvent) -> bool:
        """Return True if the event should be relayed. Other kinds are always allowed."""
        if event.kind == "like":
            return self._allow_like(event.user_key)
        if event.kind in ("share", "repost"):
            return self._allow_share(event.kind, event.user_key, event.timestamp)
        return True

    def reset(self) -> None:
        """Forget everything (new session)."""
        self._liked.clear()
        self._last_shared.clear()

    @property
    def remembered_likes(self) -> int:
        """Number of viewers whose like was already relayed."""
        return len(self._liked)

    def _allow_like(self, user_key: str) -> bool:
        """Allow only the first like of each viewer."""
        if user_key in self._liked:
            return False
        self._liked[user_key] = None
        if len(self._liked) > self._max_viewers:
            self._liked.popitem(last=False)
        return True

    def _allow_share(self, kind: str, user_key: str, now: float) -> bool:
        """Allow a share/repost unless the same viewer did it very recently."""
        self._forget_old_shares(now)
        key = (kind, user_key)
        if key in self._last_shared:
            return False
        self._last_shared[key] = now
        if len(self._last_shared) > self._max_viewers:
            self._last_shared.popitem(last=False)
        return True

    def _forget_old_shares(self, now: float) -> None:
        """Drop share entries that are older than the repeat window."""
        while self._last_shared:
            oldest_key, oldest_time = next(iter(self._last_shared.items()))
            if now - oldest_time < self.repeat_window:
                break
            del self._last_shared[oldest_key]
