"""Tests for turning TikTokLive events into RelayEvents (no network)."""

from types import SimpleNamespace
from typing import Any

import pytest

from streambridge.sources.tiktok import (
    FALLBACK_VIEWER_NAME,
    clean_name,
    clean_username,
    map_comment,
    map_gift,
    map_like,
    map_social,
    social_raw_data,
)


def user(nickname: str | None = "Budi", unique_id: str = "budi_77") -> SimpleNamespace:
    """A fake TikTok user."""
    return SimpleNamespace(nickname=nickname, unique_id=unique_id)


def social(key: str, **fields: Any) -> SimpleNamespace:
    """A fake SocialEvent with a display key."""
    common = SimpleNamespace(display_text=SimpleNamespace(key=key))
    return SimpleNamespace(user=user(), common=common, **fields)


# --- usernames and names --------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "grndpagaming",
        "@grndpagaming",
        " @grndpagaming ",
        "https://www.tiktok.com/@grndpagaming/live",
    ],
)
def test_clean_username(value: str) -> None:
    """Any common way of writing the username gives the bare name."""
    assert clean_username(value) == "grndpagaming"


def test_clean_name_removes_invisible_characters() -> None:
    """Control and zero-width characters are removed; spaces are collapsed."""
    assert clean_name("Bu​di\n  Santoso\x00") == "Budi Santoso"


def test_clean_name_keeps_emoji() -> None:
    """Emoji (including joined family emoji) stay."""
    assert clean_name("Sari 👨‍👩‍👧 🌸") == "Sari 👨‍👩‍👧 🌸"


def test_clean_name_is_limited() -> None:
    """Very long names are cut to 50 characters."""
    name = clean_name("x" * 80)
    assert len(name) == 50
    assert name.endswith("…")


@pytest.mark.parametrize("value", [None, "", "   ", "​​"])
def test_clean_name_fallback(value: str | None) -> None:
    """An empty or invisible name uses the fallback."""
    assert clean_name(value) == FALLBACK_VIEWER_NAME


# --- comments -------------------------------------------------------------


def test_comment_becomes_chat() -> None:
    """A comment keeps its text, the display name and the @handle."""
    event = map_comment(SimpleNamespace(user=user(), content="  halo kak  "))
    assert event is not None
    assert (event.kind, event.user, event.user_id, event.text) == (
        "chat",
        "Budi",
        "budi_77",
        "halo kak",
    )
    assert event.platform == "tiktok"


def test_empty_comment_is_ignored() -> None:
    """Empty comments produce nothing."""
    assert map_comment(SimpleNamespace(user=user(), content="   ")) is None


def test_viewer_without_nickname_uses_handle() -> None:
    """If the display name is empty, the @handle is shown."""
    event = map_comment(SimpleNamespace(user=user(nickname=""), content="hi"))
    assert event is not None
    assert event.user == "budi_77"


def test_missing_user_does_not_crash() -> None:
    """An event without user data still works."""
    event = map_comment(SimpleNamespace(user=None, content="hi"))
    assert event is not None
    assert event.user == FALLBACK_VIEWER_NAME
    assert event.user_id == ""


# --- gifts ----------------------------------------------------------------


def gift_event(streaking: bool, repeat_count: int = 1, name: str = "Rose") -> SimpleNamespace:
    """A fake GiftEvent."""
    return SimpleNamespace(
        user=user(), gift=SimpleNamespace(name=name), streaking=streaking, repeat_count=repeat_count
    )


def test_gift_ignored_while_streaking() -> None:
    """Taps during a streak are not relayed."""
    assert map_gift(gift_event(streaking=True, repeat_count=3)) is None


def test_gift_relayed_when_streak_ends() -> None:
    """The final event carries the full count."""
    event = map_gift(gift_event(streaking=False, repeat_count=15))
    assert event is not None
    assert (event.kind, event.gift_name, event.gift_count) == ("gift", "Rose", 15)


def test_gift_without_name_is_ignored() -> None:
    """Broken gift data produces nothing."""
    assert map_gift(gift_event(streaking=False, name="")) is None
    assert map_gift(SimpleNamespace(user=user(), gift=None, streaking=False)) is None


def test_gift_count_is_at_least_one() -> None:
    """A zero count from TikTok still means one gift."""
    event = map_gift(gift_event(streaking=False, repeat_count=0))
    assert event is not None
    assert event.gift_count == 1


# --- likes and social events ------------------------------------------------


def test_like() -> None:
    """A like event becomes a like for that viewer."""
    event = map_like(SimpleNamespace(user=user(), count=15, total=900))
    assert (event.kind, event.user_id) == ("like", "budi_77")


@pytest.mark.parametrize(
    ("key", "kind"),
    [
        ("pm_main_follow_message_viewer_2", "follow"),
        ("pm_mt_guidance_share", "share"),
        ("pm_mt_guidance_viewer_5_share", "share"),
        # Seen on a real LIVE (2026-11-02): repost has its own key, action=4.
        ("ttlive_repost_commentsarea_repostedusername_im", "repost"),
    ],
)
def test_social_kinds(key: str, kind: str) -> None:
    """Follow, share and (if TikTok marks it) repost are told apart by the display key."""
    event = map_social(social(key))
    assert event is not None
    assert event.kind == kind


def test_unknown_social_event_is_ignored() -> None:
    """Social events we do not understand are not relayed."""
    assert map_social(social("pm_something_else")) is None
    assert map_social(SimpleNamespace(user=user(), common=None)) is None


def test_social_raw_data() -> None:
    """Raw fields are collected for investigating reposts."""
    raw = social_raw_data(social("pm_mt_guidance_share", share_type=2, action=3, scene="live"))
    assert raw["key"] == "pm_mt_guidance_share"
    assert raw["share_type"] == 2
    assert raw["user"] == "budi_77"
