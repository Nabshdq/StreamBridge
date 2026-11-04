"""Where StreamBridge keeps its files on disk.

Normal locations on Windows:

- settings: ``%APPDATA%\\StreamBridge\\config.json``
- logs: ``%LOCALAPPDATA%\\StreamBridge\\logs\\``

Set the environment variable ``STREAMBRIDGE_HOME`` to put everything in one
folder instead (used by tests and for development).
"""

import os
from pathlib import Path

APP_NAME = "StreamBridge"
HOME_OVERRIDE_ENV = "STREAMBRIDGE_HOME"
CONFIG_FILE_NAME = "config.json"


def _home_override() -> Path | None:
    """Return the override folder from ``STREAMBRIDGE_HOME``, if it is set."""
    value = os.environ.get(HOME_OVERRIDE_ENV, "").strip()
    return Path(value) if value else None


def _windows_folder(env_name: str, fallback: str) -> Path:
    """Return a Windows special folder from the environment, with a fallback."""
    value = os.environ.get(env_name, "").strip()
    return Path(value) if value else Path.home() / fallback


def config_dir() -> Path:
    """Folder for settings (roams with the Windows user profile)."""
    override = _home_override()
    if override is not None:
        return override
    return _windows_folder("APPDATA", "AppData/Roaming") / APP_NAME


def config_file() -> Path:
    """Full path of ``config.json``."""
    return config_dir() / CONFIG_FILE_NAME


def quota_file() -> Path:
    """Small state file with the YouTube quota used today (never holds secrets)."""
    return config_dir() / "youtube_quota.json"


def log_dir() -> Path:
    """Folder for log files (stays on this PC)."""
    override = _home_override()
    if override is not None:
        return override / "logs"
    return _windows_folder("LOCALAPPDATA", "AppData/Local") / APP_NAME / "logs"


def resources_dir() -> Path:
    """Folder with bundled read-only files (translations, word lists).

    During development this is ``<repo>/resources``. Packaging (Phase 7)
    copies the same folder next to the app.
    """
    # src/streambridge/core/paths.py -> parents[3] is the repo root.
    return Path(__file__).resolve().parents[3] / "resources"
