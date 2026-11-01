"""Tests for YouTube compact mode."""

from streambridge.core.batching import ChatBatcher

PREFIX = "💬 TikTok:"


def test_joins_chat_after_window() -> None:
    """Chat is joined into one message when the window ends."""
    batcher = ChatBatcher(PREFIX, window=10.0)
    batcher.add("Budi", "halo", now=0.0)
    batcher.add("Sari", "nice", now=2.0)
    assert batcher.pop_due(now=9.9) == []
    assert batcher.pop_due(now=10.0) == ["💬 TikTok: Budi: halo · Sari: nice"]
    assert len(batcher) == 0
    assert batcher.pop_due(now=30.0) == []


def test_message_never_exceeds_limit() -> None:
    """Every joined message fits in 200 characters."""
    batcher = ChatBatcher(PREFIX, max_length=200)
    for number in range(40):
        batcher.add(f"viewer{number}", "pesan yang lumayan panjang", now=0.0)
    for message in batcher.flush_all():
        assert len(message) <= 200


def test_overflow_waits_for_next_batch() -> None:
    """Lines that do not fit are kept, not lost, and start the next window."""
    batcher = ChatBatcher(PREFIX, window=10.0, max_length=40)
    batcher.add("Budi", "halo semua", now=0.0)
    batcher.add("Sari", "selamat malam", now=1.0)
    first = batcher.pop_due(now=10.0)
    assert first == ["💬 TikTok: Budi: halo semua"]
    assert len(batcher) == 1
    assert batcher.pop_due(now=15.0) == []
    assert batcher.pop_due(now=20.0) == ["💬 TikTok: Sari: selamat malam"]


def test_single_long_line_is_truncated() -> None:
    """One line longer than the limit is shortened with an ellipsis."""
    batcher = ChatBatcher(PREFIX, max_length=50)
    batcher.add("Budi", "x" * 100, now=0.0)
    [message] = batcher.flush_all()
    assert len(message) == 50
    assert message.endswith("…")


def test_too_much_pending_chat_drops_oldest() -> None:
    """If chat piles up past max_pending, the oldest lines are dropped and counted."""
    batcher = ChatBatcher(PREFIX, max_pending=5)
    dropped = sum(batcher.add("Budi", f"m{number}", now=0.0) for number in range(8))
    assert dropped == 3
    assert batcher.dropped_count == 3
    assert len(batcher) == 5


def test_flush_all_empties_everything() -> None:
    """On stop, all waiting chat is released."""
    batcher = ChatBatcher(PREFIX)
    batcher.add("Budi", "halo", now=0.0)
    assert batcher.flush_all() == ["💬 TikTok: Budi: halo"]
    assert batcher.flush_all() == []
