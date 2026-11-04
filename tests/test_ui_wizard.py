"""Tests for the first-run wizard rules. They only ever touch a temporary config file."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from streambridge.core.config import AppConfig, load_config, save_config  # noqa: E402
from streambridge.core.secrets import MemoryStore  # noqa: E402
from streambridge.ui.settings_bridge import SettingsBridge  # noqa: E402
from streambridge.ui.translator import UiTranslator  # noqa: E402
from streambridge.ui.wizard import WizardController, wizard_steps  # noqa: E402


def make(tmp_path: Path, config: AppConfig | None = None) -> tuple[WizardController, Path]:
    path = tmp_path / "config.json"
    if config is not None:
        save_config(config, path)
    settings = SettingsBridge(UiTranslator("en"), path, MemoryStore())
    return WizardController(settings), path


def walk(wizard: WizardController) -> list[str]:
    """Press Next until the last step and return every step id seen."""
    seen = [wizard.step]
    while wizard.stepNumber < wizard.stepCount:
        wizard.next()
        seen.append(wizard.step)
    return seen


def fill_in_username(wizard: WizardController) -> None:
    wizard.next()  # welcome -> tiktok
    wizard.setUsernameDraft("budi_live")


def test_steps_depend_on_the_chosen_destinations() -> None:
    assert wizard_steps(True, False) == ["welcome", "tiktok", "destinations", "twitch", "done"]
    assert wizard_steps(False, True) == ["welcome", "tiktok", "destinations", "youtube", "done"]
    assert wizard_steps(True, True) == [
        "welcome",
        "tiktok",
        "destinations",
        "twitch",
        "youtube",
        "done",
    ]


def test_opens_on_first_run_only(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    assert wizard.active
    assert wizard.step == "welcome"
    again, _ = make(tmp_path / "second", AppConfig(setup_complete=True))
    assert not again.active


def test_twitch_only_skips_the_youtube_step(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    fill_in_username(wizard)
    wizard.next()
    wizard._settings.setTwitchEnabled(True)
    assert walk(wizard) == ["destinations", "twitch", "done"]


def test_youtube_only_skips_the_twitch_step(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    fill_in_username(wizard)
    wizard.next()
    wizard._settings.setYoutubeEnabled(True)
    assert walk(wizard) == ["destinations", "youtube", "done"]


def test_both_destinations_show_both_steps(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    fill_in_username(wizard)
    wizard.next()
    wizard._settings.setTwitchEnabled(True)
    wizard._settings.setYoutubeEnabled(True)
    assert walk(wizard) == ["destinations", "twitch", "youtube", "done"]
    assert wizard.stepCount == 6


def test_back_walks_the_same_steps_in_reverse(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    fill_in_username(wizard)
    wizard.next()
    wizard._settings.setTwitchEnabled(True)
    wizard._settings.setYoutubeEnabled(True)
    walk(wizard)
    seen = [wizard.step]
    while wizard.canGoBack:
        wizard.back()
        seen.append(wizard.step)
    assert seen == ["done", "youtube", "twitch", "destinations", "tiktok", "welcome"]
    assert not wizard.canGoBack


def test_changing_destinations_after_going_back_changes_the_route(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    fill_in_username(wizard)
    wizard.next()
    wizard._settings.setTwitchEnabled(True)
    wizard.next()
    assert wizard.step == "twitch"
    wizard.back()
    wizard._settings.setTwitchEnabled(False)
    wizard._settings.setYoutubeEnabled(True)
    wizard.next()
    assert wizard.step == "youtube"
    assert wizard.stepCount == 5


def test_the_open_step_falls_back_when_it_disappears(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    fill_in_username(wizard)
    wizard.next()
    wizard._settings.setTwitchEnabled(True)
    wizard.next()
    wizard._settings.setTwitchEnabled(False)  # for example changed from another place
    assert wizard.step == "destinations"


def test_next_needs_a_username_even_before_the_box_loses_focus(tmp_path: Path) -> None:
    wizard, path = make(tmp_path)
    wizard.next()
    assert wizard.step == "tiktok"
    assert not wizard.canGoNext
    wizard.setUsernameDraft("  @ ")
    assert not wizard.canGoNext  # a lone @ is still empty
    wizard.next()
    assert wizard.step == "tiktok"
    wizard.setUsernameDraft("@budi_live")
    assert wizard.canGoNext
    wizard.next()
    assert wizard.step == "destinations"
    assert load_config(path).tiktok.username == "budi_live"


def test_next_needs_at_least_one_destination(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    fill_in_username(wizard)
    wizard.next()
    assert wizard.step == "destinations"
    assert not wizard.canGoNext
    wizard.next()
    assert wizard.step == "destinations"
    wizard._settings.setYoutubeEnabled(True)
    assert wizard.canGoNext


def test_finish_is_saved_and_the_wizard_stays_away_next_time(tmp_path: Path) -> None:
    wizard, path = make(tmp_path)
    fill_in_username(wizard)
    wizard.next()
    wizard._settings.setTwitchEnabled(True)
    walk(wizard)
    assert wizard.step == "done"
    wizard.finish()
    assert not wizard.active
    assert load_config(path).setup_complete
    reopened = WizardController(SettingsBridge(UiTranslator("en"), path, MemoryStore()))
    assert not reopened.active


def test_first_run_cannot_be_closed_but_a_rerun_can(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    assert not wizard.canClose
    wizard.close()
    assert wizard.active
    finished, _ = make(tmp_path / "done", AppConfig(setup_complete=True))
    finished.restart()
    assert finished.active
    assert finished.step == "welcome"
    assert finished.canClose
    finished.close()
    assert not finished.active


def test_rerun_starts_from_the_saved_username(tmp_path: Path) -> None:
    config = AppConfig(setup_complete=True)
    config.tiktok.username = "maria"
    wizard, _ = make(tmp_path, config)
    wizard.restart()
    wizard.next()
    assert wizard.usernameDraft == "maria"
    assert wizard.canGoNext


def test_screens_are_told_when_the_step_count_changes(tmp_path: Path) -> None:
    wizard, _ = make(tmp_path)
    fired: list[int] = []
    wizard.changed.connect(lambda: fired.append(1))
    wizard._settings.setTwitchEnabled(True)
    assert fired
