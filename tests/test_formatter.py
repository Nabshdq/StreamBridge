"""Tests for message templates."""

import pytest

from streambridge.core.events import RelayEvent
from streambridge.core.formatter import (
    DEFAULT_GIFT_ICON,
    MessageFormatter,
    default_templates,
    gift_icon,
    truncate,
)
from streambridge.core.i18n import Translator


def make_formatter(language: str = "en", max_length: int = 500, **custom: str) -> MessageFormatter:
    """Make a formatter with the default templates of ``language``."""
    return MessageFormatter(default_templates(Translator(language)), max_length, custom)


EVENTS = {
    "chat": RelayEvent(kind="chat", platform="tiktok", user="Budi", text="halo"),
    "gift": RelayEvent(kind="gift", platform="tiktok", user="Budi", gift_name="Rose", gift_count=3),
    "follow": RelayEvent(kind="follow", platform="tiktok", user="Budi"),
    "like": RelayEvent(kind="like", platform="tiktok", user="Budi"),
    "share": RelayEvent(kind="share", platform="tiktok", user="Budi"),
    "repost": RelayEvent(kind="repost", platform="tiktok", user="Budi"),
}


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("chat", "💬 [TikTok] Budi: halo"),
        ("gift", "🎁 [TikTok] Budi sent Rose 🌹 x3"),
        ("follow", "⭐ [TikTok] Budi followed"),
        ("like", "❤️ [TikTok] Budi liked the LIVE"),
        ("share", "🔗 [TikTok] Budi shared the LIVE"),
        ("repost", "🔁 [TikTok] Budi reposted the LIVE"),
    ],
)
def test_english_defaults(kind: str, expected: str) -> None:
    """Default English templates match the spec."""
    assert make_formatter("en").format(EVENTS[kind]) == expected


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("chat", "💬 [TikTok] Budi: halo"),
        ("gift", "🎁 [TikTok] Budi mengirim Rose 🌹 x3"),
        ("follow", "⭐ [TikTok] Budi mulai mengikuti"),
        ("like", "❤️ [TikTok] Budi menyukai LIVE"),
        ("share", "🔗 [TikTok] Budi membagikan LIVE"),
        ("repost", "🔁 [TikTok] Budi me-repost LIVE"),
    ],
)
def test_indonesian_defaults(kind: str, expected: str) -> None:
    """Default Indonesian templates match the spec."""
    assert make_formatter("id").format(EVENTS[kind]) == expected


def test_custom_template_is_used() -> None:
    """A user template replaces the default for its kind only."""
    formatter = make_formatter(chat="{user} bilang: {message}")
    assert formatter.format(EVENTS["chat"]) == "Budi bilang: halo"
    assert formatter.format(EVENTS["follow"]) == "⭐ [TikTok] Budi followed"


def test_braces_in_viewer_text_are_safe() -> None:
    """Viewers typing {user} or { do not break formatting."""
    event = RelayEvent(kind="chat", platform="tiktok", user="Budi", text="{user} {0} {")
    assert make_formatter().format(event) == "💬 [TikTok] Budi: {user} {0} {"


@pytest.mark.parametrize("broken", ["{user", "{0}", "{user.name}", "{user:>}}"])
def test_broken_template_falls_back(broken: str) -> None:
    """A broken user template uses the default instead of crashing."""
    formatter = make_formatter(chat=broken)
    assert formatter.format(EVENTS["chat"]) == "💬 [TikTok] Budi: halo"


def test_unknown_placeholder_is_kept() -> None:
    """An unknown placeholder stays visible so the user can spot the typo."""
    formatter = make_formatter(chat="{user}: {mesage}")
    assert formatter.format(EVENTS["chat"]) == "Budi: {mesage}"


def test_message_is_truncated_to_limit() -> None:
    """Long messages are cut to the destination limit with an ellipsis."""
    event = RelayEvent(kind="chat", platform="tiktok", user="Budi", text="a" * 300)
    message = make_formatter(max_length=200).format(event)
    assert len(message) == 200
    assert message.endswith("…")


def test_truncate_short_text_unchanged() -> None:
    """Text within the limit is not changed."""
    assert truncate("halo", 10) == "halo"


def test_gift_icon_lookup() -> None:
    """Known gifts get their emoji; unknown gifts get a gift box."""
    assert gift_icon(" ROSE ") == "🌹"
    assert gift_icon("Something New") == DEFAULT_GIFT_ICON
