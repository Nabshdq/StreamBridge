"""Tests for file locations and logging setup."""

import logging
from pathlib import Path

import pytest

from streambridge.core import logging_setup, paths


def test_override_puts_everything_in_one_folder(tmp_home: Path) -> None:
    """STREAMBRIDGE_HOME redirects config and logs."""
    assert paths.config_file() == tmp_home / "config.json"
    assert paths.log_dir() == tmp_home / "logs"


def test_windows_locations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without the override, APPDATA and LOCALAPPDATA are used."""
    monkeypatch.delenv(paths.HOME_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert paths.config_file() == tmp_path / "Roaming" / "StreamBridge" / "config.json"
    assert paths.log_dir() == tmp_path / "Local" / "StreamBridge" / "logs"


def test_resources_dir_is_repo_folder() -> None:
    """The resources folder sits at the repo root, next to src/."""
    assert paths.resources_dir().name == "resources"
    assert (paths.resources_dir().parent / "src" / "streambridge").is_dir()


def test_setup_logging_writes_file(tmp_home: Path) -> None:
    """Log records end up in the rotating log file."""
    log_file = logging_setup.setup_logging(console_level=None)
    logging.getLogger("streambridge.test").warning("hello log")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert log_file.parent == tmp_home / "logs"
    assert "hello log" in log_file.read_text(encoding="utf-8")


def test_setup_logging_twice_does_not_duplicate(tmp_home: Path) -> None:
    """Calling setup_logging again replaces its handlers."""
    logging_setup.setup_logging(console_level=logging.WARNING)
    count_after_first = len(logging.getLogger().handlers)
    logging_setup.setup_logging(console_level=logging.WARNING)
    assert len(logging.getLogger().handlers) == count_after_first
    logging_setup._remove_installed_handlers(logging.getLogger())
