"""The first-run wizard: which steps to show and what the buttons may do.

The steps depend on the destinations the user picks: someone who only uses
Twitch never sees the YouTube step, and the other way round. The rules live
here, in plain Python, so they can be tested without a window.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from streambridge.ui.settings_bridge import SettingsBridge, clean_username

WELCOME = "welcome"
TIKTOK = "tiktok"
DESTINATIONS = "destinations"
TWITCH = "twitch"
YOUTUBE = "youtube"
DONE = "done"


def wizard_steps(twitch: bool, youtube: bool) -> list[str]:
    """Return the step ids to show, in order, for the chosen destinations."""
    steps = [WELCOME, TIKTOK, DESTINATIONS]
    if twitch:
        steps.append(TWITCH)
    if youtube:
        steps.append(YOUTUBE)
    steps.append(DONE)
    return steps


class WizardController(QObject):
    """Tells the wizard screens which step is open and which buttons work."""

    changed = Signal()

    def __init__(self, settings: SettingsBridge, parent: QObject | None = None) -> None:
        """Create the controller; it opens by itself until the wizard was finished once.

        Args:
            settings: Where the user's answers are saved (live, like in Settings).
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._settings = settings
        self._active = not settings.config.setup_complete
        self._step = WELCOME
        self._username_draft = settings.config.tiktok.username
        # Destination switches change the list of steps, so tell the screens too.
        settings.changed.connect(self.changed)

    # --- Rules ---------------------------------------------------------------

    def _steps(self) -> list[str]:
        config = self._settings.config
        return wizard_steps(config.twitch.enabled, config.youtube.enabled)

    def _index(self) -> int:
        """Position of the open step; a step that vanished falls back to the destinations."""
        steps = self._steps()
        if self._step not in steps:
            self._step = DESTINATIONS
        return steps.index(self._step)

    def _can_go_next(self) -> bool:
        if self._step == TIKTOK:
            return clean_username(self._username_draft) != ""
        if self._step == DESTINATIONS:
            config = self._settings.config
            return config.twitch.enabled or config.youtube.enabled
        return True

    # --- Properties for QML --------------------------------------------------

    active = Property(bool, lambda self: self._active, notify=changed)  # type: ignore[arg-type]
    step = Property(str, lambda self: self._steps()[self._index()], notify=changed)  # type: ignore[arg-type]
    stepNumber = Property(int, lambda self: self._index() + 1, notify=changed)  # type: ignore[arg-type]
    stepCount = Property(int, lambda self: len(self._steps()), notify=changed)  # type: ignore[arg-type]
    canGoBack = Property(bool, lambda self: self._index() > 0, notify=changed)  # type: ignore[arg-type]
    canGoNext = Property(bool, lambda self: self._can_go_next(), notify=changed)  # type: ignore[arg-type]
    usernameDraft = Property(str, lambda self: self._username_draft, notify=changed)  # type: ignore[arg-type]
    # The first run cannot be closed half-way (nothing works without a setup);
    # a re-run from Settings can.
    canClose = Property(bool, lambda self: self._settings.config.setup_complete, notify=changed)  # type: ignore[arg-type]

    # --- Commands from QML ---------------------------------------------------

    @Slot()
    def restart(self) -> None:
        """Open the wizard again from the first step (used by Settings)."""
        self._step = WELCOME
        self._username_draft = self._settings.config.tiktok.username
        self._active = True
        self.changed.emit()

    @Slot(str)
    def setUsernameDraft(self, text: str) -> None:
        """Remember what is being typed so Next can work before the box loses focus."""
        self._username_draft = text
        self.changed.emit()

    @Slot()
    def next(self) -> None:
        """Go to the next step (only if this step is filled in)."""
        if not self._can_go_next():
            return
        if self._step == TIKTOK:
            self._settings.setTiktokUsername(self._username_draft)
        steps = self._steps()
        position = self._index()
        if position < len(steps) - 1:
            self._step = steps[position + 1]
        self.changed.emit()

    @Slot()
    def back(self) -> None:
        """Go to the previous step."""
        position = self._index()
        if position > 0:
            self._step = self._steps()[position - 1]
        self.changed.emit()

    @Slot()
    def finish(self) -> None:
        """Close the wizard and remember that it does not need to open again."""
        self._settings.markSetupComplete()
        self._active = False
        self.changed.emit()

    @Slot()
    def close(self) -> None:
        """Close a re-run of the wizard without finishing it."""
        if self._settings.config.setup_complete:
            self._active = False
            self.changed.emit()
