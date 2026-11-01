"""Tests for translations."""

import json
from pathlib import Path

import pytest

from streambridge.core import i18n
from streambridge.core.events import EVENT_KINDS


def test_english_and_indonesian_have_same_keys() -> None:
    """Every text exists in both languages."""
    english = i18n.load_strings("en")
    indonesian = i18n.load_strings("id")
    assert english
    assert english.keys() == indonesian.keys()


def test_every_event_kind_has_a_template() -> None:
    """Each event kind has a default relay template."""
    english = i18n.load_strings("en")
    for kind in EVENT_KINDS:
        assert f"relay.template.{kind}" in english


@pytest.mark.parametrize("setting", ["en", "id"])
def test_resolve_explicit_language(setting: str) -> None:
    """An explicit language is used as is."""
    assert i18n.resolve_language(setting) == setting


def test_resolve_auto_and_unknown() -> None:
    """Auto follows the system; unknown values fall back to English."""
    assert i18n.resolve_language("auto") in i18n.SUPPORTED_LANGUAGES
    assert i18n.resolve_language("fr") == "en"


def test_auto_uses_system_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto picks Indonesian when the system language is Indonesian."""
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "id")
    assert i18n.resolve_language("auto") == "id"


def test_translator_texts() -> None:
    """The translator returns the right language."""
    assert i18n.Translator("id").text("relay.link_placeholder") == "[mengirim tautan]"
    assert i18n.Translator("en").text("relay.link_placeholder") == "[sent a link]"


def test_translator_falls_back_to_english(tmp_path: Path) -> None:
    """A key missing in Indonesian comes from English; an unknown key returns itself."""
    (tmp_path / "en.json").write_text(json.dumps({"a": "A", "b": "B"}), encoding="utf-8")
    (tmp_path / "id.json").write_text(json.dumps({"a": "A-id"}), encoding="utf-8")
    translator = i18n.Translator("id", directory=tmp_path)
    assert translator.text("a") == "A-id"
    assert translator.text("b") == "B"
    assert translator.text("missing.key") == "missing.key"


def test_broken_translation_file_does_not_crash(tmp_path: Path) -> None:
    """An unreadable file gives an empty dict instead of an exception."""
    (tmp_path / "en.json").write_text("{not json", encoding="utf-8")
    assert i18n.load_strings("en", directory=tmp_path) == {}
