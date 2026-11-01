"""Tests for the chat filter (rude words, spam, links)."""

import pytest

from streambridge.core.events import RelayEvent
from streambridge.core.filters import (
    DEFAULT_SPAM_PHRASES,
    REASON_DUPLICATE,
    REASON_EMPTY,
    REASON_SPAM,
    MessageFilter,
    ProfanityCensor,
    build_word_list,
    contains_link,
    load_default_profanity,
)

LINK_TEXT = "[mengirim tautan]"


def chat(text: str, user: str = "Budi", timestamp: float = 1000.0) -> RelayEvent:
    """Make a chat event."""
    return RelayEvent(kind="chat", platform="tiktok", user=user, text=text, timestamp=timestamp)


@pytest.fixture
def message_filter() -> MessageFilter:
    """A filter with the default spam phrases and bundled rude words."""
    return MessageFilter(
        spam_phrases=DEFAULT_SPAM_PHRASES,
        profanity_words=load_default_profanity(),
        link_text=LINK_TEXT,
    )


# --- rude words ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("anjing lu", "a****g lu"),
        ("ANJING", "A****G"),
        ("anjiiing", "a******g"),
        ("anjingnya kabur", "a****gnya kabur"),
        ("what the fuck", "what the f**k"),
        ("asu", "a*u"),
    ],
)
def test_rude_words_are_lightly_censored(text: str, expected: str) -> None:
    """The first and last letter stay; the rest becomes *."""
    censor = ProfanityCensor(load_default_profanity())
    assert censor.censor(text) == expected


@pytest.mark.parametrize("text", ["asumsi saya benar", "laptop asus baru", "babinsa datang"])
def test_harmless_words_are_not_censored(text: str) -> None:
    """Only whole rude words match, not parts of other words."""
    censor = ProfanityCensor(load_default_profanity())
    assert censor.censor(text) == text


def test_censored_chat_is_still_relayed(message_filter: MessageFilter) -> None:
    """Censoring changes the text but does not drop the message."""
    result = message_filter.check(chat("anjing seru banget"))
    assert not result.dropped
    assert result.event is not None
    assert result.event.text == "a****g seru banget"


def test_viewer_name_is_censored_for_any_kind(message_filter: MessageFilter) -> None:
    """Rude viewer names are censored, also for gifts."""
    gift = RelayEvent(kind="gift", platform="tiktok", user="bangsat", gift_name="Rose")
    result = message_filter.check(gift)
    assert result.event is not None
    assert result.event.user == "b*****t"


def test_word_list_add_and_allow() -> None:
    """Users can add rude words and allow default ones."""
    words = build_word_list(defaults=["babi", "anjing"], extra=["Kampret"], allowed=["BABI"])
    assert words == ["anjing", "kampret"]


def test_empty_word_list_changes_nothing() -> None:
    """Without words, the censor leaves text alone."""
    assert ProfanityCensor([]).censor("anjing") == "anjing"


# --- spam ---------------------------------------------------------------


@pytest.mark.parametrize("text", ["follow me guys", "Cek BIO aku ya", "gratis koin di sini"])
def test_spam_is_dropped(message_filter: MessageFilter, text: str) -> None:
    """Messages with a spam phrase are not relayed."""
    result = message_filter.check(chat(text))
    assert result.dropped
    assert result.reason == REASON_SPAM


def test_same_message_within_five_seconds_is_dropped(message_filter: MessageFilter) -> None:
    """A viewer repeating the same text quickly is spam."""
    assert not message_filter.check(chat("halo", timestamp=1000.0)).dropped
    repeat = message_filter.check(chat("HALO ", timestamp=1003.0))
    assert repeat.dropped
    assert repeat.reason == REASON_DUPLICATE


def test_same_message_after_five_seconds_passes(message_filter: MessageFilter) -> None:
    """After the window the same text is allowed again."""
    assert not message_filter.check(chat("halo", timestamp=1000.0)).dropped
    assert not message_filter.check(chat("halo", timestamp=1005.1)).dropped


def test_same_text_from_other_viewer_passes(message_filter: MessageFilter) -> None:
    """Different viewers may say the same thing."""
    assert not message_filter.check(chat("halo", user="Budi")).dropped
    assert not message_filter.check(chat("halo", user="Sari")).dropped


def test_duplicate_cache_is_bounded() -> None:
    """The repeat cache never grows past its limit."""
    message_filter = MessageFilter([], [], LINK_TEXT, max_duplicate_entries=100)
    for number in range(1000):
        message_filter.check(chat(f"pesan {number}", timestamp=1000.0))
    assert message_filter.cache_size <= 100


def test_duplicate_cache_forgets_old_entries() -> None:
    """Entries older than the window are removed."""
    message_filter = MessageFilter([], [], LINK_TEXT)
    for number in range(50):
        message_filter.check(chat(f"pesan {number}", timestamp=1000.0))
    message_filter.check(chat("baru", timestamp=2000.0))
    assert message_filter.cache_size == 1


def test_empty_chat_is_dropped(message_filter: MessageFilter) -> None:
    """Whitespace-only chat is not relayed."""
    result = message_filter.check(chat("   "))
    assert result.dropped
    assert result.reason == REASON_EMPTY


# --- links --------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["cek ini https://example.com", "www.contoh.com", "mampir ke tokoku.shop ya", "bit.ly/abc"],
)
def test_link_message_becomes_notice(message_filter: MessageFilter, text: str) -> None:
    """A message with a link is replaced by the link notice."""
    result = message_filter.check(chat(text))
    assert result.event is not None
    assert result.event.text == LINK_TEXT


@pytest.mark.parametrize("text", ["halo.semua", "jam 10.30 ya", "mantap bang"])
def test_normal_text_is_not_a_link(text: str) -> None:
    """Dots in normal text are not mistaken for links."""
    assert not contains_link(text)


# --- other kinds --------------------------------------------------------


@pytest.mark.parametrize("kind", ["gift", "follow", "like", "share", "repost"])
def test_non_chat_events_pass(message_filter: MessageFilter, kind: str) -> None:
    """Only chat text is filtered."""
    event = RelayEvent(kind=kind, platform="tiktok", user="Budi")
    assert message_filter.check(event).event == event
