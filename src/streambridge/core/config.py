"""Load and save user settings (``config.json``).

Tokens and API keys are **never** stored here; they go to the Windows
Credential Manager (``secrets.py``, Phase 3).

Loading is forgiving: unknown keys are ignored, wrong values fall back to the
default, and a corrupt file is renamed to ``config.json.bak`` so the app can
still start.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from streambridge.core import paths
from streambridge.core.events import EVENT_KINDS
from streambridge.core.filters import DEFAULT_SPAM_PHRASES
from streambridge.core.gifts import DEFAULT_GIFT_DELAY
from streambridge.core.i18n import AUTO_LANGUAGE, LANGUAGE_SETTINGS

logger = logging.getLogger(__name__)

CONFIG_VERSION = 1


@dataclass
class EventToggles:
    """Which event kinds a destination receives. All on by default."""

    chat: bool = True
    gift: bool = True
    follow: bool = True
    like: bool = True
    share: bool = True
    repost: bool = True

    def is_enabled(self, kind: str) -> bool:
        """True if events of ``kind`` should be sent."""
        return bool(getattr(self, kind, False))

    def as_dict(self) -> dict[str, bool]:
        """Return the toggles as ``{kind: enabled}``."""
        return {kind: self.is_enabled(kind) for kind in EVENT_KINDS}


@dataclass
class FilterSettings:
    """User-editable filter lists."""

    spam_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_SPAM_PHRASES))
    extra_rude_words: list[str] = field(default_factory=list)
    allowed_words: list[str] = field(default_factory=list)


@dataclass
class TikTokSettings:
    """The TikTok LIVE to read."""

    username: str = ""


@dataclass
class TwitchSettings:
    """Twitch destination settings."""

    enabled: bool = False
    events: EventToggles = field(default_factory=EventToggles)
    templates: dict[str, str] = field(default_factory=dict)
    use_bot_account: bool = False
    channel_name: str = ""


@dataclass
class YouTubeSettings:
    """YouTube destination settings."""

    enabled: bool = False
    events: EventToggles = field(default_factory=EventToggles)
    templates: dict[str, str] = field(default_factory=dict)
    compact_mode: bool = True
    use_bot_account: bool = False
    live_url: str = ""


@dataclass
class AppConfig:
    """All user settings."""

    version: int = CONFIG_VERSION
    ui_language: str = AUTO_LANGUAGE
    relay_language: str = AUTO_LANGUAGE
    gift_delay: float = DEFAULT_GIFT_DELAY
    tiktok: TikTokSettings = field(default_factory=TikTokSettings)
    filters: FilterSettings = field(default_factory=FilterSettings)
    twitch: TwitchSettings = field(default_factory=TwitchSettings)
    youtube: YouTubeSettings = field(default_factory=YouTubeSettings)

    def to_dict(self) -> dict[str, Any]:
        """Return the settings as plain JSON-ready data."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "AppConfig":
        """Build settings from loaded JSON, using defaults for anything missing or wrong."""
        data = data if isinstance(data, dict) else {}
        default = cls()
        return cls(
            version=CONFIG_VERSION,
            ui_language=_language(data, "ui_language"),
            relay_language=_language(data, "relay_language"),
            gift_delay=_number(data, "gift_delay", default.gift_delay),
            tiktok=TikTokSettings(username=_text(_section(data, "tiktok"), "username", "")),
            filters=_filters_from(_section(data, "filters")),
            twitch=_twitch_from(_section(data, "twitch")),
            youtube=_youtube_from(_section(data, "youtube")),
        )


def load_config(file_path: Path | None = None) -> AppConfig:
    """Load settings from disk. A missing file gives defaults (nothing is written)."""
    path = file_path or paths.config_file()
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.warning("Config file %s is unreadable (%s); using defaults", path, error)
        _keep_broken_copy(path)
        return AppConfig()
    if not isinstance(data, dict):
        logger.warning("Config file %s is not a JSON object; using defaults", path)
        _keep_broken_copy(path)
        return AppConfig()
    return AppConfig.from_dict(data)


def save_config(config: AppConfig, file_path: Path | None = None) -> None:
    """Save settings safely: write a temporary file first, then replace the old one."""
    path = file_path or paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    text = json.dumps(config.to_dict(), indent=2, ensure_ascii=False)
    temporary.write_text(text + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _keep_broken_copy(path: Path) -> None:
    """Rename a broken config file to ``<name>.bak`` so the user's data is not lost."""
    try:
        os.replace(path, path.with_name(path.name + ".bak"))
    except OSError as error:
        logger.warning("Could not back up broken config %s: %s", path, error)


# --- tolerant readers -----------------------------------------------------


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested object, or an empty dict if it is missing or wrong."""
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _bool(data: dict[str, Any], key: str, default: bool) -> bool:
    """Return a boolean value, or ``default``."""
    value = data.get(key)
    return value if isinstance(value, bool) else default


def _number(data: dict[str, Any], key: str, default: float, minimum: float = 0.0) -> float:
    """Return a number that is at least ``minimum``, or ``default``."""
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < minimum:
        return default
    return float(value)


def _text(data: dict[str, Any], key: str, default: str) -> str:
    """Return a string value (trimmed), or ``default``."""
    value = data.get(key)
    return value.strip() if isinstance(value, str) else default


def _text_list(data: dict[str, Any], key: str, default: list[str]) -> list[str]:
    """Return a list of strings, or ``default`` if the value is not a list."""
    value = data.get(key)
    if not isinstance(value, list):
        return list(default)
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _language(data: dict[str, Any], key: str) -> str:
    """Return a valid language setting, or ``"auto"``."""
    value = data.get(key)
    return value if value in LANGUAGE_SETTINGS else AUTO_LANGUAGE


def _toggles_from(data: dict[str, Any]) -> EventToggles:
    """Build event toggles (every kind defaults to on); unknown kinds are ignored."""
    return EventToggles(**{kind: _bool(data, kind, True) for kind in EVENT_KINDS})


def _templates_from(data: dict[str, Any]) -> dict[str, str]:
    """Keep only templates for known kinds with text."""
    return {
        kind: value
        for kind, value in data.items()
        if kind in EVENT_KINDS and isinstance(value, str) and value.strip()
    }


def _filters_from(data: dict[str, Any]) -> FilterSettings:
    """Build filter settings."""
    default = FilterSettings()
    return FilterSettings(
        spam_phrases=_text_list(data, "spam_phrases", default.spam_phrases),
        extra_rude_words=_text_list(data, "extra_rude_words", []),
        allowed_words=_text_list(data, "allowed_words", []),
    )


def _twitch_from(data: dict[str, Any]) -> TwitchSettings:
    """Build Twitch settings."""
    return TwitchSettings(
        enabled=_bool(data, "enabled", False),
        events=_toggles_from(_section(data, "events")),
        templates=_templates_from(_section(data, "templates")),
        use_bot_account=_bool(data, "use_bot_account", False),
        channel_name=_text(data, "channel_name", ""),
    )


def _youtube_from(data: dict[str, Any]) -> YouTubeSettings:
    """Build YouTube settings."""
    return YouTubeSettings(
        enabled=_bool(data, "enabled", False),
        events=_toggles_from(_section(data, "events")),
        templates=_templates_from(_section(data, "templates")),
        compact_mode=_bool(data, "compact_mode", True),
        use_bot_account=_bool(data, "use_bot_account", False),
        live_url=_text(data, "live_url", ""),
    )
