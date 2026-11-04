"""Startup self-check: refuse to run with a broken install instead of failing silently.

Without the bundled resources the app would still open, but with raw text keys,
missing icons and an EMPTY rude-word list (so rude words would pass uncensored).
A packaged build must never lack them, so any gap is fatal.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

from streambridge.core import paths
from streambridge.core.filters import load_default_profanity
from streambridge.core.i18n import SUPPORTED_LANGUAGES, load_strings

logger = logging.getLogger(__name__)

REQUIRED_FONTS = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf")
REQUIRED_ICONS = (
    "check",
    "circle-check",
    "circle-x",
    "clock",
    "external-link",
    "info",
    "layout-dashboard",
    "loader",
    "plus",
    "play",
    "settings",
    "square",
    "triangle-alert",
    "x",
)

_MB_ICONERROR = 0x10
_TITLE = "StreamBridge"

ShowFatal = Callable[[str, str], None]


def find_problems(root: Path | None = None) -> list[str]:
    """Return a readable line for everything missing or unusable in the resources folder."""
    folder = root or paths.resources_dir()
    problems: list[str] = []

    for language in SUPPORTED_LANGUAGES:
        # Same loader the app uses: a file that parses but is not an object counts as empty.
        if not load_strings(language, folder / "i18n"):
            problems.append(f"i18n/{language}.json")
    if not load_default_profanity(folder / "filters" / "profanity.json"):
        problems.append("filters/profanity.json")
    problems += [
        f"fonts/{name}" for name in REQUIRED_FONTS if not (folder / "fonts" / name).is_file()
    ]
    problems += [
        f"icons/{name}.svg"
        for name in REQUIRED_ICONS
        if not (folder / "icons" / f"{name}.svg").is_file()
    ]
    return problems


def fatal_message(problems: list[str], log_folder: Path) -> str:
    """Build the two-language text shown to the user (it cannot depend on translation files)."""
    listed = "\n".join(f"  - {item}" for item in problems)
    return (
        "StreamBridge cannot start: some of its own files are missing.\n"
        "Please reinstall StreamBridge.\n\n"
        "StreamBridge tidak bisa dimulai: sebagian filenya hilang.\n"
        "Silakan pasang ulang StreamBridge.\n\n"
        f"Missing / Hilang:\n{listed}\n\n"
        f"Log: {log_folder}"
    )


def show_error_box(title: str, text: str) -> None:
    """Show a Windows error box (works before Qt starts); print to stderr elsewhere."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, title, _MB_ICONERROR)
            return
        except (AttributeError, OSError):
            pass
    print(f"{title}: {text}", file=sys.stderr)


def startup_check(show_fatal: ShowFatal = show_error_box) -> bool:
    """Check the bundled files. On a problem: log an error, tell the user, return False."""
    problems = find_problems()
    if not problems:
        return True
    logger.error("Bundled resources are missing or unusable: %s", ", ".join(problems))
    show_fatal(_TITLE, fatal_message(problems, paths.log_dir()))
    return False
