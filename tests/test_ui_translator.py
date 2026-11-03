"""Tests for the runtime screen-language switch and the UI texts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from streambridge.app import QML_DIR  # noqa: E402
from streambridge.core.i18n import i18n_dir  # noqa: E402
from streambridge.ui.translator import UiTranslator, load_ui_strings  # noqa: E402


def _write(directory: Path, language: str, texts: dict[str, str]) -> None:
    (directory / f"{language}.json").write_text(json.dumps(texts), encoding="utf-8")


def test_only_ui_keys_are_exposed() -> None:
    strings = load_ui_strings("en")
    assert strings
    assert all(key.startswith("ui.") for key in strings)


def test_indonesian_texts_are_used() -> None:
    assert load_ui_strings("id")["ui.start"] == "Mulai"


def test_missing_key_falls_back_to_english(tmp_path: Path) -> None:
    _write(tmp_path, "en", {"ui.a": "A", "ui.b": "B"})
    _write(tmp_path, "id", {"ui.a": "AA"})
    strings = load_ui_strings("id", tmp_path)
    assert strings == {"ui.a": "AA", "ui.b": "B"}


def test_set_language_emits_and_changes_strings() -> None:
    translator = UiTranslator("en")
    fired: list[int] = []
    translator.strings_changed.connect(lambda: fired.append(1))
    translator.set_language("id")
    assert translator.strings["ui.start"] == "Mulai"
    assert fired == [1]


def test_same_or_unknown_language_changes_nothing() -> None:
    translator = UiTranslator("en")
    fired: list[int] = []
    translator.strings_changed.connect(lambda: fired.append(1))
    translator.set_language("en")
    translator.set_language("klingon")
    assert fired == []
    assert translator.setting == "en"


def test_every_ui_key_used_in_qml_exists_in_both_languages() -> None:
    used = set()
    for qml_file in QML_DIR.rglob("*.qml"):
        used |= set(re.findall(r'i18n\.strings\["([^"]+)"\]', qml_file.read_text(encoding="utf-8")))
    assert used, "QML should read its texts from i18n.strings"
    for language in ("en", "id"):
        known = json.loads((i18n_dir() / f"{language}.json").read_text(encoding="utf-8"))
        assert used <= set(known), f"missing in {language}: {used - set(known)}"


def test_qml_has_no_hard_coded_texts() -> None:
    offenders = [f.name for f in QML_DIR.rglob("*.qml") if "qsTr(" in f.read_text(encoding="utf-8")]
    assert offenders == []
