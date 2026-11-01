"""Tests for like/share/repost de-duplication."""

from streambridge.core.events import RelayEvent
from streambridge.core.likes import SocialDeduper


def social(kind: str, user: str = "Budi", timestamp: float = 1000.0) -> RelayEvent:
    """Make a like/share/repost event."""
    return RelayEvent(kind=kind, platform="tiktok", user=user, timestamp=timestamp)


def test_only_first_like_per_viewer() -> None:
    """A viewer's later likes are ignored."""
    deduper = SocialDeduper()
    assert deduper.allow(social("like"))
    assert not deduper.allow(social("like"))
    assert not deduper.allow(social("like", timestamp=99999.0))
    assert deduper.allow(social("like", user="Sari"))


def test_reset_starts_a_new_session() -> None:
    """After reset, the first like is relayed again."""
    deduper = SocialDeduper()
    deduper.allow(social("like"))
    deduper.reset()
    assert deduper.allow(social("like"))


def test_share_repeat_within_window_is_ignored() -> None:
    """The same viewer sharing again within 60 s is ignored."""
    deduper = SocialDeduper(repeat_window=60.0)
    assert deduper.allow(social("share", timestamp=1000.0))
    assert not deduper.allow(social("share", timestamp=1030.0))
    assert deduper.allow(social("share", timestamp=1061.0))


def test_share_and_repost_are_separate() -> None:
    """A share does not block a repost by the same viewer."""
    deduper = SocialDeduper()
    assert deduper.allow(social("share"))
    assert deduper.allow(social("repost"))


def test_other_kinds_always_allowed() -> None:
    """Chat, gifts and follows are not handled here."""
    deduper = SocialDeduper()
    for kind in ("chat", "gift", "follow"):
        assert deduper.allow(social(kind))
        assert deduper.allow(social(kind))


def test_memory_is_bounded() -> None:
    """The like memory never grows past its limit."""
    deduper = SocialDeduper(max_viewers=100)
    for number in range(1000):
        deduper.allow(social("like", user=f"viewer{number}"))
    assert deduper.remembered_likes == 100
