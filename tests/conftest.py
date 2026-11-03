"""Shared pytest fixtures."""

from pathlib import Path

import pytest

from streambridge.core import paths


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point StreamBridge's data folders at a temporary folder."""
    monkeypatch.setenv(paths.HOME_OVERRIDE_ENV, str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def english_system_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make "Auto" language resolve to English, whatever language this PC uses."""
    monkeypatch.setattr("streambridge.core.i18n.detect_system_language", lambda: "en")
