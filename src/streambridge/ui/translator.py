"""Screen texts for QML, switchable at runtime without restarting the app.

QML reads texts as ``i18n.strings["ui.start"]``. Because ``strings`` is a property
with a change signal, every text binding re-evaluates when the language changes.
A plain ``tr("key")`` slot would be called once and never again.

The texts live in the same ``resources/i18n/<language>.json`` files as the relay
texts, under the ``ui.`` prefix. English is always loaded underneath, so a key
missing in another language shows the English text instead of nothing.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from streambridge.core.i18n import (
    AUTO_LANGUAGE,
    DEFAULT_LANGUAGE,
    LANGUAGE_SETTINGS,
    load_strings,
    resolve_language,
)

UI_PREFIX = "ui."


def load_ui_strings(setting: str, directory: Path | None = None) -> dict[str, str]:
    """Return every ``ui.*`` text for a language setting, with English as the base."""
    texts = load_strings(DEFAULT_LANGUAGE, directory)
    texts.update(load_strings(resolve_language(setting), directory))
    return {key: value for key, value in texts.items() if key.startswith(UI_PREFIX)}


class UiTranslator(QObject):
    """Holds the current screen language and its texts."""

    strings_changed = Signal()
    setting_changed = Signal()

    def __init__(
        self,
        setting: str = AUTO_LANGUAGE,
        directory: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Create the translator.

        Args:
            setting: ``"auto"``, ``"en"`` or ``"id"``.
            directory: Folder with translation files. Defaults to ``resources/i18n``.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._directory = directory
        self._setting = setting if setting in LANGUAGE_SETTINGS else AUTO_LANGUAGE
        self._strings = load_ui_strings(self._setting, directory)

    strings = Property("QVariantMap", lambda self: self._strings, notify=strings_changed)  # type: ignore[arg-type]
    setting = Property(str, lambda self: self._setting, notify=setting_changed)  # type: ignore[arg-type]

    @Slot(str)
    def set_language(self, setting: str) -> None:
        """Switch the screen language. Unknown values are ignored."""
        if setting not in LANGUAGE_SETTINGS or setting == self._setting:
            return
        self._setting = setting
        self._strings = load_ui_strings(setting, self._directory)
        self.setting_changed.emit()
        self.strings_changed.emit()
