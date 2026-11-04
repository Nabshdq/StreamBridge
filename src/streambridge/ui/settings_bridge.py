"""The Settings screens' view of ``config.json``.

Every change made in the UI is validated and saved to disk straight away. Saved
settings are used by the *next* Start; a running relay keeps the settings it
started with.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from streambridge import __version__
from streambridge.core import paths
from streambridge.core.config import (
    DEFAULT_GIFT_DELAY,
    EVENT_KINDS,
    AppConfig,
    load_config,
    save_config,
)
from streambridge.core.i18n import LANGUAGE_SETTINGS
from streambridge.core.secrets import TIKTOK_EULER_KEY, KeyringStore, SecretStore
from streambridge.ui.translator import UiTranslator

logger = logging.getLogger(__name__)

GITHUB_URL = "https://github.com/Nabshdq/StreamBridge"
DESTINATIONS = ("twitch", "youtube")
WORD_LISTS = ("spam", "rude", "allowed")
MIN_GIFT_DELAY = 1.0
MAX_GIFT_DELAY = 30.0


def clamp_gift_delay(value: float) -> float:
    """Return a safe gift-merge delay in seconds for whatever the user typed."""
    if not math.isfinite(value):  # nan and +-inf cannot be a delay
        return DEFAULT_GIFT_DELAY
    return min(max(value, MIN_GIFT_DELAY), MAX_GIFT_DELAY)


def clean_username(text: str) -> str:
    """Remove spaces and a leading ``@`` from a TikTok username."""
    return text.strip().lstrip("@").strip()


class SettingsBridge(QObject):
    """Reads and writes the user's settings for QML."""

    changed = Signal()

    def __init__(
        self,
        translator: UiTranslator,
        config_path: Path | None = None,
        secrets: SecretStore | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Create the bridge.

        Args:
            translator: Switched when the screen language changes.
            config_path: Where ``config.json`` lives. ``None`` means the real
                per-user location; tests pass a temporary file.
            secrets: Where the Euler key is kept. Defaults to Windows Credential Manager.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._secrets = secrets or KeyringStore()
        self._save_error = ""
        self._path = config_path
        self._translator = translator
        self._config: AppConfig = load_config(config_path)
        self._translator.set_language(self._config.ui_language)

    @property
    def config(self) -> AppConfig:
        """The settings as currently held (already saved)."""
        return self._config

    def _save(self) -> None:
        try:
            save_config(self._config, self._path)
            self._save_error = ""
        except OSError as problem:
            logger.exception("Could not save the settings")
            self._save_error = str(problem)
        self.changed.emit()

    def _words(self, name: str) -> list[str]:
        filters = self._config.filters
        return {
            "spam": filters.spam_phrases,
            "rude": filters.extra_rude_words,
            "allowed": filters.allowed_words,
        }[name]

    # --- Properties for QML -------------------------------------------------

    uiLanguage = Property(str, lambda self: self._config.ui_language, notify=changed)  # type: ignore[arg-type]
    relayLanguage = Property(str, lambda self: self._config.relay_language, notify=changed)  # type: ignore[arg-type]
    tiktokUsername = Property(str, lambda self: self._config.tiktok.username, notify=changed)  # type: ignore[arg-type]
    giftDelay = Property(float, lambda self: self._config.gift_delay, notify=changed)  # type: ignore[arg-type]
    twitchEnabled = Property(bool, lambda self: self._config.twitch.enabled, notify=changed)  # type: ignore[arg-type]
    youtubeEnabled = Property(bool, lambda self: self._config.youtube.enabled, notify=changed)  # type: ignore[arg-type]

    saveError = Property(str, lambda self: self._save_error, notify=changed)  # type: ignore[arg-type]
    compactMode = Property(bool, lambda self: self._config.youtube.compact_mode, notify=changed)  # type: ignore[arg-type]
    spamPhrases = Property("QStringList", lambda self: list(self._words("spam")), notify=changed)  # type: ignore[arg-type]
    rudeWords = Property("QStringList", lambda self: list(self._words("rude")), notify=changed)  # type: ignore[arg-type]
    allowedWords = Property(  # type: ignore[arg-type]
        "QStringList", lambda self: list(self._words("allowed")), notify=changed
    )
    hasEulerKey = Property(  # type: ignore[arg-type]
        bool, lambda self: bool(self._secrets.get(TIKTOK_EULER_KEY)), notify=changed
    )
    appVersion = Property(str, lambda self: __version__, constant=True)  # type: ignore[arg-type]
    githubUrl = Property(str, lambda self: GITHUB_URL, constant=True)  # type: ignore[arg-type]

    @Property("QVariantMap", notify=changed)  # type: ignore[arg-type]
    def eventToggles(self) -> dict:
        """``{"twitch": {kind: bool}, "youtube": {kind: bool}}`` for the switches."""
        return {
            "twitch": self._config.twitch.events.as_dict(),
            "youtube": self._config.youtube.events.as_dict(),
        }

    # --- Commands from QML --------------------------------------------------

    @Slot(str)
    def setUiLanguage(self, setting: str) -> None:
        """Change the language of the app screens (``auto``, ``en`` or ``id``)."""
        if setting not in LANGUAGE_SETTINGS:
            return
        self._config.ui_language = setting
        self._translator.set_language(setting)
        self._save()

    @Slot(str)
    def setRelayLanguage(self, setting: str) -> None:
        """Change the language of relayed messages (``auto``, ``en`` or ``id``)."""
        if setting not in LANGUAGE_SETTINGS:
            return
        self._config.relay_language = setting
        self._save()

    @Slot(str)
    def setTiktokUsername(self, text: str) -> None:
        """Save the TikTok username to read, without ``@`` or spaces."""
        self._config.tiktok.username = clean_username(text)
        self._save()

    @Slot(float)
    def setGiftDelay(self, seconds: float) -> None:
        """Save how long identical gifts are merged, in seconds."""
        self._config.gift_delay = clamp_gift_delay(float(seconds))
        self._save()

    @Slot(bool)
    def setTwitchEnabled(self, enabled: bool) -> None:
        """Turn the Twitch destination on or off."""
        self._config.twitch.enabled = enabled
        self._save()

    @Slot(bool)
    def setYoutubeEnabled(self, enabled: bool) -> None:
        """Turn the YouTube destination on or off."""
        self._config.youtube.enabled = enabled
        self._save()

    @Slot(str, str, bool)
    def setEvent(self, destination: str, kind: str, enabled: bool) -> None:
        """Turn one event kind on or off for ``"twitch"`` or ``"youtube"``."""
        if destination not in DESTINATIONS or kind not in EVENT_KINDS:
            return
        events = getattr(self._config, destination).events
        setattr(events, kind, enabled)
        self._save()

    @Slot(bool)
    def setCompactMode(self, enabled: bool) -> None:
        """Turn YouTube compact mode (several chat lines in one message) on or off."""
        self._config.youtube.compact_mode = enabled
        self._save()

    @Slot(str, str)
    def addWord(self, list_name: str, word: str) -> None:
        """Add a word or phrase to ``"spam"``, ``"rude"`` or ``"allowed"`` (no duplicates)."""
        word = word.strip()
        if list_name not in WORD_LISTS or not word:
            return
        words = self._words(list_name)
        if word.lower() not in (w.lower() for w in words):
            words.append(word)
            self._save()

    @Slot(str, str)
    def removeWord(self, list_name: str, word: str) -> None:
        """Remove a word or phrase from one of the lists."""
        if list_name not in WORD_LISTS:
            return
        words = self._words(list_name)
        if word in words:
            words.remove(word)
            self._save()

    @Slot(str)
    def setEulerKey(self, key: str) -> None:
        """Save the optional Euler Stream API key in the Windows Credential Manager."""
        key = key.strip()
        if key:
            self._secrets.set(TIKTOK_EULER_KEY, key)
        else:
            self._secrets.delete(TIKTOK_EULER_KEY)
        self.changed.emit()

    @Slot()
    def markSetupComplete(self) -> None:
        """Remember that the first-run wizard was finished."""
        self._config.setup_complete = True
        self._save()

    @Slot()
    def openLogFolder(self) -> None:
        """Open the folder with the log files in File Explorer."""
        folder = paths.log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @Slot(str)
    def openUrl(self, url: str) -> None:
        """Open a web page in the default browser (only http and https)."""
        if url.startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(url))
