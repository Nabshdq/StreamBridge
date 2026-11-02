"""TikTok LIVE source: reads a LIVE anonymously with the TikTokLive library.

This module has two parts:

1. **Event mapping** — small functions that turn TikTokLive events into our
   ``RelayEvent``. They only read attributes, so tests can pass simple fake
   objects instead of real TikTokLive events.
2. **TikTokSource** — connects, waits while the user is not live, reconnects
   after problems, and reports its status (added below).

Facts about TikTokLive 7.0.1 used here are listed in CLAUDE.md §8.
"""

import logging
import re
import unicodedata
from typing import Any

from streambridge.core.events import RelayEvent

logger = logging.getLogger(__name__)

PLATFORM = "tiktok"
MAX_NAME_LENGTH = 50
FALLBACK_VIEWER_NAME = "TikTok viewer"

_WHITESPACE = re.compile(r"\s+")
# Zero-width joiner glues emoji together (👨‍👩‍👧); keep it.
_KEEP_FORMAT_CHARS = {"‍"}


# --- small helpers ---------------------------------------------------------


def clean_username(value: str) -> str:
    """Turn ``@name``, ``name`` or a TikTok URL into the bare username."""
    text = value.strip()
    text = re.sub(r"^https?://(www\.)?tiktok\.com/", "", text, flags=re.IGNORECASE)
    text = text.removesuffix("/live").strip("/")
    return text.removeprefix("@").strip()


def clean_name(name: str | None, fallback: str = FALLBACK_VIEWER_NAME) -> str:
    """Make a viewer name safe to show: no invisible characters, single spaces, max 50 chars."""
    if not name:
        return fallback
    visible = "".join(
        char
        for char in name
        if char in _KEEP_FORMAT_CHARS or unicodedata.category(char) not in ("Cc", "Cf")
    )
    text = _WHITESPACE.sub(" ", visible).strip()
    if not text:
        return fallback
    if len(text) > MAX_NAME_LENGTH:
        text = text[: MAX_NAME_LENGTH - 1].rstrip() + "…"
    return text


def display_key(event: Any) -> str:
    """Return the lower-case ``common.display_text.key`` of an event, or ``""``."""
    common = getattr(event, "common", None)
    display_text = getattr(common, "display_text", None)
    key = getattr(display_text, "key", "") or ""
    return str(key).lower()


def viewer_of(event: Any) -> tuple[str, str]:
    """Return ``(display name, @handle)`` of the viewer behind an event."""
    user = getattr(event, "user", None)
    handle = str(getattr(user, "unique_id", "") or "")
    name = clean_name(getattr(user, "nickname", None), fallback=handle or FALLBACK_VIEWER_NAME)
    return name, handle


def _relay_event(kind: str, event: Any, **values: Any) -> RelayEvent:
    """Build a RelayEvent with the viewer filled in."""
    name, handle = viewer_of(event)
    return RelayEvent(kind=kind, platform=PLATFORM, user=name, user_id=handle, **values)


# --- event mapping -----------------------------------------------------------


def map_comment(event: Any) -> RelayEvent | None:
    """``CommentEvent`` -> ``chat`` (empty comments are ignored)."""
    text = str(getattr(event, "content", "") or "").strip()
    if not text:
        return None
    return _relay_event("chat", event, text=text)


def map_gift(event: Any) -> RelayEvent | None:
    """``GiftEvent`` -> ``gift``, but only when a streak has ended.

    While a viewer is still tapping a streakable gift, TikTok sends one event
    per tap with ``streaking=True``; the final event has the full count.
    """
    if getattr(event, "streaking", False):
        return None
    gift = getattr(event, "gift", None)
    gift_name = str(getattr(gift, "name", "") or "").strip()
    if not gift_name:
        return None
    count = int(getattr(event, "repeat_count", 1) or 1)
    return _relay_event("gift", event, gift_name=gift_name, gift_count=max(1, count))


def map_like(event: Any) -> RelayEvent:
    """``LikeEvent`` -> ``like`` (only the first like per viewer is relayed later)."""
    return _relay_event("like", event)


def social_kind(event: Any) -> str | None:
    """Classify a ``SocialEvent`` as ``follow``, ``repost`` or ``share`` (or ``None``).

    TikTokLive itself only knows follow and share, by looking for those words in
    ``common.display_text.key``. A repost goes through TikTok's share menu; if
    its key turns out to contain "repost" it is recognised here, otherwise it
    is reported as a share. The raw data is logged so we can find out.
    """
    key = display_key(event)
    if "follow" in key:
        return "follow"
    if "repost" in key:
        return "repost"
    if "share" in key:
        return "share"
    return None


def map_social(event: Any) -> RelayEvent | None:
    """``SocialEvent`` -> ``follow`` / ``share`` / ``repost`` (unknown kinds are ignored)."""
    kind = social_kind(event)
    if kind is None:
        return None
    return _relay_event(kind, event)


def social_raw_data(event: Any) -> dict[str, Any]:
    """The raw fields of a SocialEvent that may tell a repost from a share."""
    _, handle = viewer_of(event)
    return {
        "key": display_key(event),
        "share_type": getattr(event, "share_type", None),
        "action": getattr(event, "action", None),
        "share_target": getattr(event, "share_target", None),
        "scene": getattr(event, "scene", None),
        "user": handle,
    }
