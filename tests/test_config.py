"""Tests for loading and saving settings."""

import json
from pathlib import Path

from streambridge.core.config import AppConfig, load_config, save_config
from streambridge.core.filters import DEFAULT_SPAM_PHRASES


def test_missing_file_gives_defaults_without_writing(tmp_home: Path) -> None:
    """First start: defaults are used and nothing is created yet."""
    config = load_config()
    assert config == AppConfig()
    assert not (tmp_home / "config.json").exists()


def test_defaults() -> None:
    """Defaults match the agreed behaviour."""
    config = AppConfig()
    assert config.ui_language == "auto"
    assert config.relay_language == "auto"
    assert config.gift_delay == 5.0
    assert not config.twitch.enabled
    assert not config.youtube.enabled
    assert config.youtube.compact_mode
    assert config.filters.spam_phrases == list(DEFAULT_SPAM_PHRASES)
    for kind in ("chat", "gift", "follow", "like", "share", "repost"):
        assert config.twitch.events.is_enabled(kind)
        assert config.youtube.events.is_enabled(kind)


def test_save_and_load_round_trip(tmp_home: Path) -> None:
    """What is saved is loaded back unchanged."""
    config = AppConfig()
    config.relay_language = "id"
    config.tiktok.username = "budi_live"
    config.twitch.enabled = True
    config.twitch.events.like = False
    config.youtube.templates = {"chat": "{user}: {message}"}
    config.filters.extra_rude_words = ["kampret"]
    save_config(config)
    assert load_config() == config


def test_saved_file_is_readable_json(tmp_home: Path) -> None:
    """The file on disk is pretty, UTF-8 JSON without leftover temp files."""
    save_config(AppConfig())
    path = tmp_home / "config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert not (tmp_home / "config.json.tmp").exists()


def test_no_secrets_in_config() -> None:
    """The settings structure has no place for tokens or keys."""
    text = json.dumps(AppConfig().to_dict()).lower()
    for word in ("token", "secret", "password", "api_key"):
        assert word not in text


def test_corrupt_file_is_backed_up(tmp_home: Path) -> None:
    """A broken file is kept as .bak and defaults are used."""
    path = tmp_home / "config.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert load_config() == AppConfig()
    assert (tmp_home / "config.json.bak").read_text(encoding="utf-8") == "{ this is not json"
    assert not path.exists()


def test_wrong_values_fall_back_to_defaults() -> None:
    """Bad types or values are replaced by defaults, good ones are kept."""
    data = {
        "ui_language": "klingon",
        "relay_language": "id",
        "gift_delay": -3,
        "tiktok": "not an object",
        "twitch": {"enabled": "yes", "events": {"chat": False, "unknown": True}},
        "youtube": {"compact_mode": False, "templates": {"chat": 5, "gift": "{user} {gift}"}},
        "filters": {"spam_phrases": ["promo", 7, " "]},
        "unknown_key": 1,
    }
    config = AppConfig.from_dict(data)
    assert config.ui_language == "auto"
    assert config.relay_language == "id"
    assert config.gift_delay == 5.0
    assert config.tiktok.username == ""
    assert config.twitch.enabled is False
    assert config.twitch.events.chat is False
    assert config.twitch.events.gift is True
    assert config.youtube.compact_mode is False
    assert config.youtube.templates == {"gift": "{user} {gift}"}
    assert config.filters.spam_phrases == ["promo"]


def test_non_object_file_gives_defaults(tmp_home: Path) -> None:
    """A JSON list instead of an object is treated as broken."""
    (tmp_home / "config.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert load_config() == AppConfig()
