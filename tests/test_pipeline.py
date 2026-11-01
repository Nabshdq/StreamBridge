"""Tests for the relay pipeline."""

from streambridge.core.batching import ChatBatcher
from streambridge.core.config import EventToggles
from streambridge.core.events import RelayEvent
from streambridge.core.filters import DEFAULT_SPAM_PHRASES, MessageFilter, load_default_profanity
from streambridge.core.formatter import MessageFormatter, default_templates
from streambridge.core.gifts import GiftMerger
from streambridge.core.i18n import Translator
from streambridge.core.likes import SocialDeduper
from streambridge.core.outqueue import OutQueue
from streambridge.core.pipeline import Pipeline, Route

TRANSLATOR = Translator("id")


def make_route(
    name: str,
    max_length: int = 500,
    max_queue: int | None = None,
    compact: bool = False,
    toggles: EventToggles | None = None,
) -> Route:
    """Make a route with Indonesian defaults."""
    batcher = (
        ChatBatcher(TRANSLATOR.text("relay.compact_prefix"), max_length=max_length)
        if compact
        else None
    )
    return Route(
        name=name,
        toggles=(toggles or EventToggles()).as_dict(),
        formatter=MessageFormatter(default_templates(TRANSLATOR), max_length),
        queue=OutQueue(max_queue),
        batcher=batcher,
    )


def make_pipeline(*routes: Route) -> Pipeline:
    """Make a pipeline with the default filter."""
    return Pipeline(
        message_filter=MessageFilter(
            DEFAULT_SPAM_PHRASES,
            load_default_profanity(),
            TRANSLATOR.text("relay.link_placeholder"),
        ),
        deduper=SocialDeduper(),
        gift_merger=GiftMerger(delay=5.0),
        routes=routes,
    )


def event(kind: str, user: str = "Budi", **values: object) -> RelayEvent:
    """Make an event at a fixed time."""
    return RelayEvent(kind=kind, platform="tiktok", user=user, timestamp=1000.0, **values)


def texts(route: Route) -> list[str]:
    """Drain a route's queue."""
    result = []
    while (message := route.queue.get_nowait()) is not None:
        result.append(message.text)
    return result


def test_chat_is_filtered_formatted_and_queued() -> None:
    """A normal chat ends up formatted in the queue; spam is counted."""
    twitch = make_route("twitch")
    pipeline = make_pipeline(twitch)
    pipeline.handle(event("chat", text="anjing seru"), now=0.0)
    pipeline.handle(event("chat", user="Sari", text="follow me ya"), now=0.0)
    assert texts(twitch) == ["💬 [TikTok] Budi: a****g seru"]
    assert pipeline.counters.filtered == 1


def test_routes_to_every_destination_with_own_limits() -> None:
    """Each destination gets its own copy, truncated to its own limit."""
    twitch = make_route("twitch", max_length=500)
    youtube = make_route("youtube", max_length=200)
    pipeline = make_pipeline(twitch, youtube)
    pipeline.handle(event("chat", text="a" * 400), now=0.0)
    assert len(texts(twitch)[0]) > 200
    assert len(texts(youtube)[0]) == 200


def test_event_toggles_per_destination() -> None:
    """YouTube can get gifts only while Twitch gets everything."""
    twitch = make_route("twitch")
    gifts_only = EventToggles(chat=False, follow=False, like=False, share=False, repost=False)
    youtube = make_route("youtube", toggles=gifts_only)
    pipeline = make_pipeline(twitch, youtube)
    pipeline.handle(event("chat", text="halo"), now=0.0)
    pipeline.handle(event("follow"), now=0.0)
    pipeline.handle(event("gift", gift_name="Rose"), now=0.0)
    pipeline.tick(now=5.0)
    assert len(texts(twitch)) == 3
    assert texts(youtube) == ["🎁 [TikTok] Budi mengirim Rose 🌹 x1"]


def test_gifts_are_merged_then_released_on_tick() -> None:
    """Gift streaks become one message after the delay."""
    twitch = make_route("twitch")
    pipeline = make_pipeline(twitch)
    for second in (0.0, 1.0, 2.0):
        pipeline.handle(event("gift", gift_name="Rose"), now=second)
    pipeline.tick(now=4.0)
    assert texts(twitch) == []
    pipeline.tick(now=5.0)
    assert texts(twitch) == ["🎁 [TikTok] Budi mengirim Rose 🌹 x3"]


def test_only_first_like_and_session_reset() -> None:
    """A viewer's like is relayed once per session."""
    twitch = make_route("twitch")
    pipeline = make_pipeline(twitch)
    for _ in range(5):
        pipeline.handle(event("like"), now=0.0)
    assert texts(twitch) == ["❤️ [TikTok] Budi menyukai LIVE"]
    pipeline.reset_session()
    pipeline.handle(event("like"), now=0.0)
    assert len(texts(twitch)) == 1


def test_compact_mode_batches_chat_but_not_gifts() -> None:
    """YouTube chat is joined; follows still go out on their own."""
    youtube = make_route("youtube", max_length=200, compact=True)
    pipeline = make_pipeline(youtube)
    pipeline.handle(event("chat", text="halo"), now=0.0)
    pipeline.handle(event("chat", user="Sari", text="nice"), now=1.0)
    pipeline.handle(event("follow", user="Andi"), now=1.0)
    assert texts(youtube) == ["⭐ [TikTok] Andi mulai mengikuti"]
    pipeline.tick(now=10.0)
    assert texts(youtube) == ["💬 TikTok: Budi: halo · Sari: nice"]


def test_twitch_drops_nothing_youtube_drops_old_chat() -> None:
    """With 100 chats: Twitch keeps all, YouTube keeps 30 and counts drops."""
    twitch = make_route("twitch", max_queue=None)
    youtube = make_route("youtube", max_length=200, max_queue=30)
    pipeline = make_pipeline(twitch, youtube)
    for number in range(100):
        pipeline.handle(event("chat", user=f"viewer{number}", text=f"pesan {number}"), now=0.0)
    assert len(twitch.queue) == 100
    assert pipeline.counters.dropped["twitch"] == 0
    assert len(youtube.queue) == 30
    assert pipeline.counters.dropped["youtube"] == 70


def test_flush_all_releases_gifts_and_batches() -> None:
    """On stop, held gifts and batched chat are queued, not lost."""
    youtube = make_route("youtube", max_length=200, compact=True)
    pipeline = make_pipeline(youtube)
    pipeline.handle(event("gift", gift_name="Rose"), now=0.0)
    pipeline.handle(event("chat", text="halo"), now=0.0)
    pipeline.flush_all(now=1.0)
    assert sorted(texts(youtube)) == sorted(
        ["🎁 [TikTok] Budi mengirim Rose 🌹 x1", "💬 TikTok: Budi: halo"]
    )


def test_test_message_goes_first_everywhere() -> None:
    """A test message is queued for every destination with high priority."""
    twitch = make_route("twitch")
    youtube = make_route("youtube", max_length=200)
    pipeline = make_pipeline(twitch, youtube)
    pipeline.handle(event("chat", text="halo"), now=0.0)
    pipeline.enqueue_text("StreamBridge test")
    assert texts(twitch)[0] == "StreamBridge test"
    assert texts(youtube)[0] == "StreamBridge test"
