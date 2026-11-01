"""Chat filter: censor rude words, drop spam, replace links.

Only chat text is filtered. Viewer names are censored for every event kind.

Rules, in order:

1. Spam phrase (e.g. "follow me") -> the message is dropped.
2. Same viewer sends the same text again within a few seconds -> dropped.
3. The message contains a link -> the whole text becomes a notice such as
   ``[sent a link]``.
4. Rude words are lightly censored: ``anjing`` -> ``a****g``.
"""

import json
import logging
import re
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from streambridge.core import paths
from streambridge.core.events import RelayEvent

logger = logging.getLogger(__name__)

DEFAULT_SPAM_PHRASES: tuple[str, ...] = (
    "follow me",
    "follow back",
    "follback",
    "folback",
    "f4f",
    "dm me",
    "check my bio",
    "check my profile",
    "link in bio",
    "cek bio",
    "cek profil",
    "link di bio",
    "free coins",
    "koin gratis",
    "gratis koin",
)

DEFAULT_DUPLICATE_WINDOW = 5.0
MAX_DUPLICATE_ENTRIES = 5000

REASON_SPAM = "spam"
REASON_DUPLICATE = "duplicate"
REASON_EMPTY = "empty"

# Common Indonesian word endings, so "anjingnya" is censored too. English
# forms (e.g. "bitches") are listed as separate words instead, because a
# generic "s" ending would also censor harmless words like "asus".
_WORD_SUFFIXES = r"(?:nya|lah|kah|mu|ku)?"

_LINK_PATTERN = re.compile(
    r"https?://\S+"
    r"|www\.\S+"
    r"|\b[\w-]+\.(?:com|net|org|id|co|io|ly|me|gg|tv|xyz|link|site|shop|app|info|biz|live)\b",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class FilterResult:
    """Outcome of filtering one event.

    Attributes:
        event: The (possibly changed) event, or ``None`` if it was dropped.
        reason: Why it was dropped (``"spam"``, ``"duplicate"``, ``"empty"``), else ``""``.
    """

    event: RelayEvent | None
    reason: str = ""

    @property
    def dropped(self) -> bool:
        """True if the event must not be relayed."""
        return self.event is None


def normalize(text: str) -> str:
    """Lower-case the text and collapse whitespace, for comparisons."""
    return _WHITESPACE.sub(" ", text).strip().casefold()


def contains_link(text: str) -> bool:
    """True if the text contains something that looks like a web link."""
    return _LINK_PATTERN.search(text) is not None


def load_default_profanity(file_path: Path | None = None) -> list[str]:
    """Load the bundled rude-word lists (all languages combined)."""
    path = file_path or paths.resources_dir() / "filters" / "profanity.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Could not load profanity list %s: %s", path, error)
        return []
    words: list[str] = []
    for key, values in data.items():
        if key.startswith("_") or not isinstance(values, list):
            continue
        words.extend(str(word) for word in values)
    return words


def build_word_list(
    defaults: Iterable[str], extra: Iterable[str], allowed: Iterable[str]
) -> list[str]:
    """Combine default and user-added rude words, minus the words the user allows."""
    allowed_set = {normalize(word) for word in allowed}
    result: list[str] = []
    for word in [*defaults, *extra]:
        cleaned = normalize(word)
        if cleaned and cleaned not in allowed_set and cleaned not in result:
            result.append(cleaned)
    return result


class ProfanityCensor:
    """Replaces the middle letters of rude words with ``*``."""

    def __init__(self, words: Iterable[str]) -> None:
        """Build one pattern that matches any of ``words``.

        Each letter may repeat (``anjiiing``), common endings are allowed
        (``anjingnya``), and only whole words match (``asumsi`` is left alone).
        """
        cleaned = sorted({normalize(word) for word in words if normalize(word)}, key=len)
        if not cleaned:
            self._pattern: re.Pattern[str] | None = None
            return
        alternatives = [
            "".join(re.escape(letter) + "+" for letter in word) for word in reversed(cleaned)
        ]
        self._pattern = re.compile(
            r"\b(" + "|".join(alternatives) + r")" + _WORD_SUFFIXES + r"\b",
            re.IGNORECASE,
        )

    def censor(self, text: str) -> str:
        """Return ``text`` with rude words masked, e.g. ``anjing`` -> ``a****g``."""
        if self._pattern is None:
            return text
        return self._pattern.sub(self._mask_match, text)

    @staticmethod
    def _mask_match(match: re.Match[str]) -> str:
        """Mask the rude word part of a match and keep any word ending."""
        word = match.group(1)
        ending = match.group(0)[len(word) :]
        return _mask(word) + ending


def _mask(word: str) -> str:
    """Keep the first and last letter, replace the rest with ``*``."""
    if len(word) <= 2:
        return word[0] + "*" * (len(word) - 1)
    return word[0] + "*" * (len(word) - 2) + word[-1]


class MessageFilter:
    """Applies all chat rules to incoming events."""

    def __init__(
        self,
        spam_phrases: Iterable[str],
        profanity_words: Iterable[str],
        link_text: str,
        duplicate_window: float = DEFAULT_DUPLICATE_WINDOW,
        max_duplicate_entries: int = MAX_DUPLICATE_ENTRIES,
    ) -> None:
        """Create the filter.

        Args:
            spam_phrases: Phrases that make a chat message spam.
            profanity_words: Rude words to censor.
            link_text: Text that replaces a message containing a link.
            duplicate_window: Seconds in which a repeated message is dropped.
            max_duplicate_entries: Upper bound for the repeat cache.
        """
        self._spam_phrases = [normalize(phrase) for phrase in spam_phrases if normalize(phrase)]
        self._censor = ProfanityCensor(profanity_words)
        self._link_text = link_text
        self._duplicate_window = duplicate_window
        self._max_duplicate_entries = max_duplicate_entries
        # (viewer, text) -> last time seen. Oldest entries come first.
        self._recent: OrderedDict[tuple[str, str], float] = OrderedDict()

    def check(self, event: RelayEvent) -> FilterResult:
        """Filter one event and return the result."""
        event = replace(event, user=self._censor.censor(event.user))
        if event.kind != "chat":
            return FilterResult(event)

        text = normalize(event.text)
        if not text:
            return FilterResult(None, REASON_EMPTY)
        if self._is_spam(text):
            return FilterResult(None, REASON_SPAM)
        if self._is_duplicate(event.user_key, text, event.timestamp):
            return FilterResult(None, REASON_DUPLICATE)

        if contains_link(event.text):
            return FilterResult(replace(event, text=self._link_text))
        return FilterResult(replace(event, text=self._censor.censor(event.text.strip())))

    def censor(self, text: str) -> str:
        """Censor rude words in any text."""
        return self._censor.censor(text)

    @property
    def cache_size(self) -> int:
        """Number of entries in the repeat cache (for tests and diagnostics)."""
        return len(self._recent)

    def _is_spam(self, text: str) -> bool:
        """True if the text contains a spam phrase."""
        return any(phrase in text for phrase in self._spam_phrases)

    def _is_duplicate(self, user_key: str, text: str, now: float) -> bool:
        """True if this viewer sent this text within the duplicate window."""
        self._forget_old(now)
        key = (user_key, text)
        last_seen = self._recent.get(key)
        self._recent[key] = now
        self._recent.move_to_end(key)
        while len(self._recent) > self._max_duplicate_entries:
            self._recent.popitem(last=False)
        return last_seen is not None and now - last_seen < self._duplicate_window

    def _forget_old(self, now: float) -> None:
        """Remove cache entries older than the duplicate window."""
        while self._recent:
            oldest_key, oldest_time = next(iter(self._recent.items()))
            if now - oldest_time < self._duplicate_window:
                break
            del self._recent[oldest_key]
