"""Shared pytest fixtures."""

from pathlib import Path

import pytest

from streambridge.core import paths


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point StreamBridge's data folders at a temporary folder."""
    monkeypatch.setenv(paths.HOME_OVERRIDE_ENV, str(tmp_path))
    return tmp_path
