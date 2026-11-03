"""Tests for the settings bridge. They only ever touch a temporary config file."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from streambridge.core.config import load_config  # noqa: E402
from streambridge.ui.settings_bridge import SettingsBridge, clean_username  # noqa: E402
from streambridge.ui.translator import UiTranslator  # noqa: E402


def make(tmp_path: Path) -> tuple[SettingsBridge, UiTranslator, Path]:
    path = tmp_path / "config.json"
    translator = UiTranslator("en")
    return SettingsBridge(translator, path), translator, path


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
    again = SettingsBridge(UiTranslator("en"), path)
    assert again.youtubeEnabled


def test_ui_language_switches_the_translator_and_is_reapplied_at_startup(tmp_path: Path) -> None:
    bridge, translator, path = make(tmp_path)
    bridge.setUiLanguage("id")
    assert translator.strings["ui.start"] == "Mulai"
    fresh = UiTranslator("en")
    SettingsBridge(fresh, path)
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
    SettingsBridge(translator, tmp_path / "config.json")  # no config yet: ui_language is "auto"
    assert translator.strings["ui.start"] == "Mulai"


@pytest.mark.parametrize(
    "typed,expected",
    [(0, 1.0), (-5, 1.0), (9999, 30.0), (7.5, 7.5), (float("nan"), 5.0),
     (float("inf"), 5.0), (float("-inf"), 5.0)],
)
def test_gift_delay_is_kept_in_a_safe_range(typed: float, expected: float, tmp_path: Path) -> None:
    bridge, _, path = make(tmp_path)
    bridge.setGiftDelay(typed)
    assert bridge.giftDelay == expected
    assert load_config(path).gift_delay == expected
