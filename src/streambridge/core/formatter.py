"""Turns events into chat messages using templates.

Placeholders: ``{user}``, ``{message}``, ``{gift}``, ``{count}``, ``{icon}``.
Viewer text is inserted as a value, so braces typed by viewers are harmless.
A broken template (for example ``"{user"``) falls back to the default one.
"""

import logging
from collections.abc import Mapping

from streambridge.core.events import EVENT_KINDS, RelayEvent
from streambridge.core.i18n import Translator

logger = logging.getLogger(__name__)

ELLIPSIS = "…"
TWITCH_MAX_LENGTH = 500
YOUTUBE_MAX_LENGTH = 200
DEFAULT_GIFT_ICON = "🎁"

# Emoji for common TikTok gifts, keyed by lower-case gift name.
GIFT_ICONS: dict[str, str] = {
    "rose": "🌹",
    "tiktok": "🎵",
    "heart me": "💗",
    "finger heart": "🫰",
    "hand hearts": "🫶",
    "ice cream cone": "🍦",
    "doughnut": "🍩",
    "gg": "🎮",
    "sunglasses": "😎",
    "cap": "🧢",
    "corgi": "🐶",
    "confetti": "🎊",
    "fireworks": "🎆",
    "money gun": "💸",
    "train": "🚂",
    "sports car": "🏎️",
    "galaxy": "🌌",
    "lion": "🦁",
    "universe": "🪐",
}

_FORMAT_ERRORS = (ValueError, IndexError, KeyError, AttributeError, TypeError)


class _KeepUnknown(dict[str, str]):
    """Leaves unknown placeholders such as ``{foo}`` in the text unchanged."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def gift_icon(gift_name: str) -> str:
    """Return an emoji for the gift, or a generic gift box."""
    return GIFT_ICONS.get(gift_name.strip().casefold(), DEFAULT_GIFT_ICON)


def truncate(text: str, max_length: int) -> str:
    """Shorten ``text`` to ``max_length`` characters, ending with ``…`` if cut."""
    if len(text) <= max_length:
        return text
    if max_length <= len(ELLIPSIS):
        return text[:max_length]
    return text[: max_length - len(ELLIPSIS)].rstrip() + ELLIPSIS


def default_templates(translator: Translator) -> dict[str, str]:
    """Return the default template for every event kind in the translator's language."""
    return {kind: translator.text(f"relay.template.{kind}") for kind in EVENT_KINDS}


def render(template: str, event: RelayEvent) -> str:
    """Fill a template with the event's values. Raises on a broken template."""
    values = _KeepUnknown(
        user=event.user,
        message=event.text,
        gift=event.gift_name,
        count=str(event.gift_count),
        icon=gift_icon(event.gift_name),
    )
    return template.format_map(values).strip()


class MessageFormatter:
    """Formats events for one destination."""

    def __init__(
        self,
        defaults: Mapping[str, str],
        max_length: int,
        custom_templates: Mapping[str, str] | None = None,
    ) -> None:
        """Create a formatter.

        Args:
            defaults: Default template per event kind (from ``default_templates``).
            max_length: Maximum message length of the destination.
            custom_templates: Templates the user wrote; missing kinds use the default.
        """
        self._defaults = dict(defaults)
        self._custom = {kind: text for kind, text in (custom_templates or {}).items() if text}
        self.max_length = max_length

    def format(self, event: RelayEvent) -> str:
        """Return the finished, length-limited message for ``event``."""
        default = self._defaults.get(event.kind, "{user}")
        template = self._custom.get(event.kind, default)
        try:
            text = render(template, event)
        except _FORMAT_ERRORS as error:
            logger.warning("Broken %s template %r (%s); using default", event.kind, template, error)
            text = render(default, event)
        return truncate(text, self.max_length)
