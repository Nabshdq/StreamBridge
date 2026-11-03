"""The Settings screens' view of ``config.json``.

Every change made in the UI is validated and saved to disk straight away. Saved
settings are used by the *next* Start; a running relay keeps the settings it
started with.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from streambridge.core.config import DEFAULT_GIFT_DELAY, AppConfig, load_config, save_config
from streambridge.core.i18n import LANGUAGE_SETTINGS
from streambridge.ui.translator import UiTranslator

logger = logging.getLogger(__name__)

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
        parent: QObject | None = None,
    ) -> None:
        """Create the bridge.

        Args:
            translator: Switched when the screen language changes.
            config_path: Where ``config.json`` lives. ``None`` means the real
                per-user location; tests pass a temporary file.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
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
        except OSError:
            logger.exception("Could not save the settings")
        self.changed.emit()

    # --- Properties for QML -------------------------------------------------

    uiLanguage = Property(str, lambda self: self._config.ui_language, notify=changed)  # type: ignore[arg-type]
    relayLanguage = Property(str, lambda self: self._config.relay_language, notify=changed)  # type: ignore[arg-type]
    tiktokUsername = Property(str, lambda self: self._config.tiktok.username, notify=changed)  # type: ignore[arg-type]
    giftDelay = Property(float, lambda self: self._config.gift_delay, notify=changed)  # type: ignore[arg-type]
    twitchEnabled = Property(bool, lambda self: self._config.twitch.enabled, notify=changed)  # type: ignore[arg-type]
    youtubeEnabled = Property(bool, lambda self: self._config.youtube.enabled, notify=changed)  # type: ignore[arg-type]

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
