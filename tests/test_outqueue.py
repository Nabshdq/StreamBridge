"""Tests for the outgoing priority queue."""

import asyncio

from streambridge.core.outqueue import YOUTUBE_MAX_QUEUE, OutMessage, OutQueue


def msg(kind: str, text: str = "") -> OutMessage:
    """Make a message of ``kind``."""
    return OutMessage.for_kind(text or kind, kind)


def drain(queue: OutQueue) -> list[str]:
    """Take every message and return their texts."""
    texts = []
    while (message := queue.get_nowait()) is not None:
        texts.append(message.text)
    return texts


def test_high_priority_leaves_first() -> None:
    """Gifts, follows, shares and reposts go before chat and likes."""
    queue = OutQueue()
    for kind in ("chat", "like", "gift", "follow", "share", "repost"):
        queue.put(msg(kind))
    assert drain(queue) == ["gift", "follow", "share", "repost", "chat", "like"]


def test_same_priority_keeps_order() -> None:
    """Messages of equal priority leave in arrival order."""
    queue = OutQueue()
    for number in range(5):
        queue.put(msg("chat", f"chat {number}"))
    assert drain(queue) == [f"chat {number}" for number in range(5)]


def test_unlimited_queue_never_drops() -> None:
    """Twitch: 1000 chat messages in, 1000 out, nothing dropped."""
    queue = OutQueue(max_size=None)
    for number in range(1000):
        assert queue.put(msg("chat", f"chat {number}")) is None
    assert len(queue) == 1000
    assert queue.dropped_count == 0
    assert drain(queue) == [f"chat {number}" for number in range(1000)]


def test_full_queue_drops_oldest_chat() -> None:
    """YouTube: past the limit, the oldest chat is dropped."""
    queue = OutQueue(max_size=YOUTUBE_MAX_QUEUE)
    for number in range(YOUTUBE_MAX_QUEUE):
        queue.put(msg("chat", f"chat {number}"))
    dropped = queue.put(msg("chat", "newest"))
    assert dropped is not None
    assert dropped.text == "chat 0"
    assert len(queue) == YOUTUBE_MAX_QUEUE
    assert queue.dropped_count == 1


def test_full_queue_never_drops_gifts() -> None:
    """High-priority messages stay even when the queue is over its limit."""
    queue = OutQueue(max_size=3)
    queue.put(msg("chat", "old chat"))
    for number in range(5):
        queue.put(msg("gift", f"gift {number}"))
    texts = drain(queue)
    assert texts == [f"gift {number}" for number in range(5)]
    assert queue.dropped_count == 1


async def test_get_waits_for_a_message() -> None:
    """get() blocks until something is put."""
    queue = OutQueue()
    waiter = asyncio.create_task(queue.get())
    await asyncio.sleep(0.01)
    assert not waiter.done()
    queue.put(msg("follow"))
    message = await asyncio.wait_for(waiter, timeout=1)
    assert message.kind == "follow"
