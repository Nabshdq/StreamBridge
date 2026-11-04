"""Tests for the startup self-check (a broken install must fail loudly)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

from streambridge.core import paths, selfcheck


@pytest.fixture
def resources_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private copy of the real resources folder that tests may damage."""
    copy = tmp_path / "resources"
    shutil.copytree(paths.resources_dir(), copy)
    monkeypatch.setattr(paths, "resources_dir", lambda: copy)
    return copy


def test_real_resources_pass() -> None:
    """The bundled files in the source tree are complete."""
    assert selfcheck.find_problems() == []


def test_required_icons_match_the_icon_folder() -> None:
    """A new icon file must be added to REQUIRED_ICONS too (and the other way round)."""
    on_disk = {path.stem for path in (paths.resources_dir() / "icons").glob("*.svg")}
    assert set(selfcheck.REQUIRED_ICONS) == on_disk


def test_required_fonts_match_the_font_folder() -> None:
    """Same guard for the fonts."""
    on_disk = {path.name for path in (paths.resources_dir() / "fonts").glob("*.ttf")}
    assert set(selfcheck.REQUIRED_FONTS) == on_disk


def test_empty_folder_reports_everything(tmp_path: Path) -> None:
    """With nothing in the folder, every group of files is reported."""
    problems = selfcheck.find_problems(tmp_path)
    assert "i18n/en.json" in problems
    assert "i18n/id.json" in problems
    assert "filters/profanity.json" in problems
    assert "fonts/Inter-Regular.ttf" in problems
    assert "icons/play.svg" in problems


def test_missing_icon_is_reported(resources_copy: Path) -> None:
    """One missing icon is enough to be named."""
    (resources_copy / "icons" / "play.svg").unlink()
    assert selfcheck.find_problems() == ["icons/play.svg"]


def test_profanity_file_with_the_wrong_shape_counts_as_empty(resources_copy: Path) -> None:
    """A file that parses but yields no words is the silent failure we are closing."""
    (resources_copy / "filters" / "profanity.json").write_text('{"en": "not a list"}')
    assert selfcheck.find_problems() == ["filters/profanity.json"]


def test_translation_file_that_is_not_an_object_counts_as_empty(resources_copy: Path) -> None:
    """A translation file with the wrong shape is reported."""
    (resources_copy / "i18n" / "id.json").write_text("[]")
    assert selfcheck.find_problems() == ["i18n/id.json"]


def test_startup_check_passes_quietly() -> None:
    """A complete install shows nothing."""
    shown: list[str] = []
    assert selfcheck.startup_check(lambda title, text: shown.append(text)) is True
    assert shown == []


def test_startup_check_fails_loudly(
    resources_copy: Path, caplog: pytest.LogCaptureFixture, tmp_home: Path
) -> None:
    """A broken install logs an ERROR, tells the user in both languages and says no."""
    (resources_copy / "icons" / "play.svg").unlink()
    shown: list[tuple[str, str]] = []
    with caplog.at_level(logging.ERROR):
        ok = selfcheck.startup_check(lambda title, text: shown.append((title, text)))
    assert ok is False
    assert any(record.levelno == logging.ERROR for record in caplog.records)
    (title, text) = shown[0]
    assert title == "StreamBridge"
    assert "icons/play.svg" in text
    assert "reinstall" in text.lower()
    assert "pasang ulang" in text.lower()
    assert str(paths.log_dir()) in text
