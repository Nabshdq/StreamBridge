"""Tests for the gift combo merger."""

from streambridge.core.events import RelayEvent
from streambridge.core.gifts import GiftMerger


def gift(name: str = "Rose", user: str = "Budi", count: int = 1) -> RelayEvent:
    """Make a gift event."""
    return RelayEvent(kind="gift", platform="tiktok", user=user, gift_name=name, gift_count=count)


def test_gifts_in_window_are_summed() -> None:
    """Rose at 0 s and 3 s become one 'Rose x2' at 5 s."""
    merger = GiftMerger(delay=5.0)
    merger.add(gift(), now=0.0)
    merger.add(gift(), now=3.0)
    assert merger.pop_due(now=4.9) == []
    released = merger.pop_due(now=5.0)
    assert len(released) == 1
    assert released[0].gift_count == 2


def test_window_is_fixed_from_first_gift() -> None:
    """A gift after the window starts a new group."""
    merger = GiftMerger(delay=5.0)
    merger.add(gift(), now=0.0)
    merger.add(gift(), now=3.0)
    first = merger.pop_due(now=5.0)
    merger.add(gift(), now=6.0)
    second = merger.pop_due(now=11.0)
    assert [event.gift_count for event in first + second] == [2, 1]


def test_counts_from_events_are_added() -> None:
    """A gift event that already carries a count is summed correctly."""
    merger = GiftMerger(delay=5.0)
    merger.add(gift(count=5), now=0.0)
    merger.add(gift(count=10), now=1.0)
    assert merger.pop_due(now=5.0)[0].gift_count == 15


def test_different_gifts_and_viewers_are_separate() -> None:
    """Grouping is per (viewer, gift)."""
    merger = GiftMerger(delay=5.0)
    merger.add(gift("Rose", "Budi"), now=0.0)
    merger.add(gift("Galaxy", "Budi"), now=0.0)
    merger.add(gift("Rose", "Sari"), now=0.0)
    assert len(merger.pop_due(now=5.0)) == 3


def test_flush_all_releases_everything() -> None:
    """On stop, buffered gifts are released instead of dropped."""
    merger = GiftMerger(delay=5.0)
    merger.add(gift(), now=0.0)
    merger.add(gift(), now=1.0)
    released = merger.flush_all()
    assert len(released) == 1
    assert released[0].gift_count == 2
    assert len(merger) == 0


def test_zero_delay_releases_immediately() -> None:
    """With delay 0 every gift is due at once."""
    merger = GiftMerger(delay=0.0)
    merger.add(gift(), now=10.0)
    assert len(merger.pop_due(now=10.0)) == 1
