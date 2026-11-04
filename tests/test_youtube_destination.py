"""Tests for the YouTube destination (the Google client is a fake)."""

import json
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from streambridge.core.quota import QuotaTracker
from streambridge.core.secrets import MemoryStore
from streambridge.destinations.base import TemporarySendError
from streambridge.destinations.youtube import (
    LOOKUP_INTERVAL,
    REASON_LOGIN,
    REASON_QUOTA,
    YouTubeDestination,
    video_id_from_url,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def http_error(status: int, reason: str = "") -> HttpError:
    body = {"error": {"errors": [{"reason": reason}]}} if reason else {}
    return HttpError(MagicMock(status=status), json.dumps(body).encode("utf-8"))


def live_broadcast(chat_id="chat-1", status="live") -> dict:
    return {"status": {"lifeCycleStatus": status}, "snippet": {"liveChatId": chat_id}}


def make(tmp_path, live_url="", service=None):
    service = service or MagicMock()
    clock = Clock()
    quota = QuotaTracker(tmp_path / "q.json", clock=lambda: 1_800_000_000.0)
    destination = YouTubeDestination(
        MemoryStore(), quota, live_url=live_url, service_factory=lambda: service, clock=clock
    )
    return destination, service, quota, clock


def set_broadcasts(service, items) -> None:
    service.liveBroadcasts.return_value.list.return_value.execute.return_value = {"items": items}


def insert_call(service) -> MagicMock:
    return service.liveChatMessages.return_value.insert


async def test_sends_to_the_live_chat_and_counts_quota(tmp_path):
    destination, service, quota, _ = make(tmp_path)
    set_broadcasts(service, [live_broadcast("chat-1")])
    result = await destination.send("hello")
    assert result.ok
    body = insert_call(service).call_args.kwargs["body"]
    assert body["snippet"]["liveChatId"] == "chat-1"
    assert body["snippet"]["textMessageDetails"]["messageText"] == "hello"
    assert quota.used == 1 + 20  # one look-up + one insert


async def test_lookup_uses_mine_only_and_picks_the_live_one(tmp_path):
    destination, service, _, _ = make(tmp_path)
    set_broadcasts(service, [live_broadcast("old", "complete"), live_broadcast("now", "live")])
    await destination.send("hi")
    kwargs = service.liveBroadcasts.return_value.list.call_args.kwargs
    assert kwargs == {"part": "snippet,status", "mine": True}  # no second filter
    assert insert_call(service).call_args.kwargs["body"]["snippet"]["liveChatId"] == "now"


async def test_chat_id_is_looked_up_only_once(tmp_path):
    destination, service, quota, _ = make(tmp_path)
    set_broadcasts(service, [live_broadcast()])
    await destination.send("a")
    await destination.send("b")
    assert service.liveBroadcasts.return_value.list.call_count == 1
    assert quota.used == 1 + 20 + 20


async def test_waits_for_live_and_throttles_lookups(tmp_path):
    destination, service, quota, clock = make(tmp_path)
    set_broadcasts(service, [])
    with pytest.raises(TemporarySendError):
        await destination.send("a")
    with pytest.raises(TemporarySendError):  # too soon: no new API call
        await destination.send("a")
    assert service.liveBroadcasts.return_value.list.call_count == 1
    assert destination.waiting_for_live
    clock.now += LOOKUP_INTERVAL
    set_broadcasts(service, [live_broadcast()])
    assert (await destination.send("a")).ok
    assert service.liveBroadcasts.return_value.list.call_count == 2
    assert quota.used == 1 + 1 + 20


async def test_bot_mode_uses_the_live_url(tmp_path):
    destination, service, _, _ = make(tmp_path, live_url="https://youtu.be/VID123")
    service.videos.return_value.list.return_value.execute.return_value = {
        "items": [{"liveStreamingDetails": {"activeLiveChatId": "bot-chat"}}]
    }
    await destination.send("hi")
    assert service.videos.return_value.list.call_args.kwargs == {
        "part": "liveStreamingDetails",
        "id": "VID123",
    }
    service.liveBroadcasts.assert_not_called()
    assert insert_call(service).call_args.kwargs["body"]["snippet"]["liveChatId"] == "bot-chat"


async def test_quota_exhausted_locally_refuses_without_calling_google(tmp_path):
    destination, service, quota, _ = make(tmp_path)
    quota.record(9990)
    result = await destination.send("hi")
    assert not result.ok
    assert result.reason == REASON_QUOTA
    service.liveBroadcasts.assert_not_called()


async def test_quota_exceeded_from_google_is_a_refusal_not_a_retry(tmp_path):
    destination, service, _, _ = make(tmp_path)
    set_broadcasts(service, [live_broadcast()])
    insert_call(service).return_value.execute.side_effect = http_error(403, "quotaExceeded")
    result = await destination.send("hi")
    assert (result.ok, result.reason) == (False, REASON_QUOTA)


@pytest.mark.parametrize(
    "error",
    [http_error(403, "rateLimitExceeded"), http_error(429), http_error(503), OSError("offline")],
)
async def test_temporary_problems_are_retried(tmp_path, error):
    destination, service, _, _ = make(tmp_path)
    set_broadcasts(service, [live_broadcast()])
    insert_call(service).return_value.execute.side_effect = error
    with pytest.raises(TemporarySendError):
        await destination.send("hi")


async def test_live_that_ended_triggers_a_new_lookup(tmp_path):
    destination, service, _, clock = make(tmp_path)
    set_broadcasts(service, [live_broadcast("old-chat")])
    await destination.send("a")
    insert_call(service).return_value.execute.side_effect = http_error(403, "liveChatEnded")
    with pytest.raises(TemporarySendError):
        await destination.send("b")
    assert destination.waiting_for_live


async def test_expired_login_is_reported(tmp_path):
    destination, service, _, _ = make(tmp_path)
    set_broadcasts(service, [live_broadcast()])
    insert_call(service).return_value.execute.side_effect = http_error(401)
    result = await destination.send("hi")
    assert (result.ok, result.reason) == (False, REASON_LOGIN)


async def test_other_refusals_are_not_retried(tmp_path):
    destination, service, _, _ = make(tmp_path)
    set_broadcasts(service, [live_broadcast()])
    insert_call(service).return_value.execute.side_effect = http_error(400, "invalidMessage")
    result = await destination.send("hi")
    assert not result.ok
    assert result.reason == "invalidMessage"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=abc123&t=5", "abc123"),
        ("https://youtu.be/abc123", "abc123"),
        ("https://www.youtube.com/live/abc123", "abc123"),
        ("https://m.youtube.com/watch?v=abc123", "abc123"),
        ("https://example.com/watch?v=abc123", None),
        ("not a url", None),
    ],
)
def test_video_id_from_url(url, expected):
    assert video_id_from_url(url) == expected
