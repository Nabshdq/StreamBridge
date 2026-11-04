"""Tests for the settings bridge. They only ever touch a temporary config file."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from streambridge.core.config import load_config  # noqa: E402
from streambridge.core.secrets import TIKTOK_EULER_KEY, MemoryStore  # noqa: E402
from streambridge.ui.settings_bridge import SettingsBridge, clean_username  # noqa: E402
from streambridge.ui.translator import UiTranslator  # noqa: E402


def make(tmp_path: Path) -> tuple[SettingsBridge, UiTranslator, Path]:
    path = tmp_path / "config.json"
    translator = UiTranslator("en")
    return SettingsBridge(translator, path, MemoryStore()), translator, path


def test_changes_are_saved_to_disk(tmp_path: Path) -> None:
    bridge, _, path = make(tmp_path)
    bridge.setTiktokUsername("  @maria ")
    bridge.setTwitchEnabled(True)
    bridge.setRelayLanguage("id")
    saved = load_config(path)
    assert saved.tiktok.username == "maria"
    assert saved.twitch.enabled
    assert saved.relay_language == "id"


def test_settings_survive_a_restart(tmp_path: Path) -> None:
    bridge, _, path = make(tmp_path)
    bridge.setYoutubeEnabled(True)
    again = SettingsBridge(UiTranslator("en"), path, MemoryStore())
    assert again.youtubeEnabled


def test_ui_language_switches_the_translator_and_is_reapplied_at_startup(tmp_path: Path) -> None:
    bridge, translator, path = make(tmp_path)
    bridge.setUiLanguage("id")
    assert translator.strings["ui.start"] == "Mulai"
    fresh = UiTranslator("en")
    SettingsBridge(fresh, path, MemoryStore())
    assert fresh.setting == "id"


def test_unknown_language_is_rejected(tmp_path: Path) -> None:
    bridge, _, _ = make(tmp_path)
    bridge.setUiLanguage("klingon")
    bridge.setRelayLanguage("klingon")
    assert bridge.uiLanguage == "auto"
    assert bridge.relayLanguage == "auto"


def test_changed_signal_fires(tmp_path: Path) -> None:
    bridge, _, _ = make(tmp_path)
    fired: list[int] = []
    bridge.changed.connect(lambda: fired.append(1))
    bridge.setTwitchEnabled(True)
    assert fired == [1]


@pytest.mark.parametrize("text,expected", [("@a", "a"), ("  b  ", "b"), ("@ c", "c"), ("", "")])
def test_clean_username(text: str, expected: str) -> None:
    assert clean_username(text) == expected


def test_auto_language_follows_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("streambridge.core.i18n.detect_system_language", lambda: "id")
    translator = UiTranslator("auto")
    # No config file yet, so ui_language is "auto".
    SettingsBridge(translator, tmp_path / "config.json", MemoryStore())
    assert translator.strings["ui.start"] == "Mulai"


@pytest.mark.parametrize(
    "typed,expected",
    [
        (0, 1.0),
        (-5, 1.0),
        (9999, 30.0),
        (7.5, 7.5),
        (float("nan"), 5.0),
        (float("inf"), 5.0),
        (float("-inf"), 5.0),
    ],
)
def test_gift_delay_is_kept_in_a_safe_range(typed: float, expected: float, tmp_path: Path) -> None:
    bridge, _, path = make(tmp_path)
    bridge.setGiftDelay(typed)
    assert bridge.giftDelay == expected
    assert load_config(path).gift_delay == expected


def test_event_toggles_are_per_destination_and_saved(tmp_path: Path) -> None:
    bridge, _, path = make(tmp_path)
    assert bridge.eventToggles["youtube"]["follow"] is False  # YouTube defaults
    assert bridge.eventToggles["twitch"]["follow"] is True
    bridge.setEvent("youtube", "follow", True)
    bridge.setEvent("twitch", "like", False)
    saved = load_config(path)
    assert saved.youtube.events.follow
    assert not saved.twitch.events.like
    assert bridge.eventToggles["youtube"]["follow"] is True


def test_unknown_event_or_destination_is_ignored(tmp_path: Path) -> None:
    bridge, _, _ = make(tmp_path)
    bridge.setEvent("kick", "chat", False)
    bridge.setEvent("twitch", "dance", False)
    assert bridge.eventToggles["twitch"]["chat"] is True


def test_word_lists_add_remove_and_ignore_duplicates(tmp_path: Path) -> None:
    bridge, _, path = make(tmp_path)
    bridge.addWord("rude", "  Foo ")
    bridge.addWord("rude", "foo")  # duplicate, any case
    bridge.addWord("rude", "   ")
    bridge.addWord("nonsense", "x")
    assert bridge.rudeWords == ["Foo"]
    assert load_config(path).filters.extra_rude_words == ["Foo"]
    bridge.removeWord("rude", "Foo")
    assert bridge.rudeWords == []


def test_default_spam_phrases_can_be_edited(tmp_path: Path) -> None:
    bridge, _, _ = make(tmp_path)
    first = bridge.spamPhrases[0]
    bridge.removeWord("spam", first)
    assert first not in bridge.spamPhrases


def test_euler_key_goes_to_the_secret_store_not_to_config(tmp_path: Path) -> None:
    store = MemoryStore()
    path = tmp_path / "config.json"
    bridge = SettingsBridge(UiTranslator("en"), path, store)
    assert not bridge.hasEulerKey
    bridge.setEulerKey(" secret-key ")
    assert store.get(TIKTOK_EULER_KEY) == "secret-key"
    assert bridge.hasEulerKey
    assert not path.exists() or "secret-key" not in path.read_text(encoding="utf-8")
    bridge.setEulerKey("")
    assert not bridge.hasEulerKey


def test_save_failure_is_reported_and_cleared(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    bridge = SettingsBridge(UiTranslator("en"), blocker / "config.json", MemoryStore())
    bridge.setTwitchEnabled(True)
    assert bridge.saveError != ""
    assert bridge.twitchEnabled  # still shown, but the user is told it was not saved
    blocker.unlink()
    bridge.setTwitchEnabled(False)
    assert bridge.saveError == ""


def test_compact_mode_is_saved(tmp_path: Path) -> None:
    bridge, _, path = make(tmp_path)
    bridge.setCompactMode(False)
    assert load_config(path).youtube.compact_mode is False


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        (4.0, 4.0),
        (0.0, 0.5),
        (-2.0, 0.5),
        (99.0, 12.0),
        (float("nan"), 3.0),
        (float("inf"), 3.0),
    ],
)
def test_live_hours_are_kept_in_a_safe_range(typed: float, expected: float, tmp_path: Path) -> None:
    bridge, _, path = make(tmp_path)
    assert bridge.liveHours == 3.0
    bridge.setLiveHours(typed)
    assert bridge.liveHours == expected
    assert load_config(path).youtube.live_hours == expected
