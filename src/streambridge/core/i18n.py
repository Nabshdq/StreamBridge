"""Translations for relay messages (and later the app UI).

Text lives in ``resources/i18n/<language>.json`` as flat ``"key": "text"`` pairs.
Missing keys fall back to English, then to the key itself, so a missing
translation never crashes the app.
"""

import json
import locale
import logging
import sys
from pathlib import Path

from streambridge.core import paths

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "id")
DEFAULT_LANGUAGE = "en"
AUTO_LANGUAGE = "auto"
LANGUAGE_SETTINGS: tuple[str, ...] = (AUTO_LANGUAGE, *SUPPORTED_LANGUAGES)

# Windows primary language id for Indonesian (LANG_INDONESIAN).
_WINDOWS_LANG_INDONESIAN = 0x21


def i18n_dir() -> Path:
    """Folder that holds the translation JSON files."""
    return paths.resources_dir() / "i18n"


def detect_system_language() -> str:
    """Return ``"id"`` if the Windows display language is Indonesian, else ``"en"``."""
    if sys.platform == "win32":
        try:
            import ctypes

            language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        except (AttributeError, OSError):
            return DEFAULT_LANGUAGE
        primary_language = language_id & 0x3FF
        return "id" if primary_language == _WINDOWS_LANG_INDONESIAN else DEFAULT_LANGUAGE

    language_code = (locale.getlocale()[0] or "").lower()
    return "id" if language_code.startswith(("id", "indonesian")) else DEFAULT_LANGUAGE


def resolve_language(setting: str) -> str:
    """Turn a language setting (``"auto"``, ``"en"``, ``"id"``) into a real language."""
    if setting in SUPPORTED_LANGUAGES:
        return setting
    if setting == AUTO_LANGUAGE:
        return detect_system_language()
    return DEFAULT_LANGUAGE


def load_strings(language: str, directory: Path | None = None) -> dict[str, str]:
    """Load all texts for one language. Returns an empty dict if the file is unusable."""
    file_path = (directory or i18n_dir()) / f"{language}.json"
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Could not load translations %s: %s", file_path, error)
        return {}
    if not isinstance(data, dict):
        logger.warning("Translation file %s is not a JSON object", file_path)
        return {}
    return {str(key): str(value) for key, value in data.items()}


class Translator:
    """Looks up texts for one language, with English as the fallback."""

    def __init__(self, language: str, directory: Path | None = None) -> None:
        """Create a translator.

        Args:
            language: A language setting (``"auto"``, ``"en"`` or ``"id"``).
            directory: Folder with translation files. Defaults to ``resources/i18n``.
        """
        self.language = resolve_language(language)
        self._strings = load_strings(self.language, directory)
        self._fallback = (
            self._strings
            if self.language == DEFAULT_LANGUAGE
            else load_strings(DEFAULT_LANGUAGE, directory)
        )

    def text(self, key: str) -> str:
        """Return the text for ``key`` in this language (English or the key if missing)."""
        if key in self._strings:
            return self._strings[key]
        if key in self._fallback:
            return self._fallback[key]
        logger.warning("Missing translation key: %s", key)
        return key
