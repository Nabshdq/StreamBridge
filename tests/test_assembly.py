"""Tests for building the engine from the user's settings."""

import pytest

from streambridge.core.assembly import (
    SetupError,
    assemble_engine,
    build_destinations,
    build_source,
    route_options_from_config,
)
from streambridge.core.config import AppConfig
from streambridge.core.engine import RelayEngine
from streambridge.core.secrets import TIKTOK_EULER_KEY, MemoryStore
from streambridge.destinations.base import Destination
from streambridge.destinations.console import ConsoleDestination
from streambridge.sources.tiktok import TikTokSource
from tests.test_engine import ListSource


def console_factory(name: str):
    """A factory that always creates a console destination called ``name``."""

    def factory(config: AppConfig, store: MemoryStore) -> Destination:
        return ConsoleDestination(name)

    return factory


def not_set_up(config: AppConfig, store: MemoryStore) -> Destination | None:
    """A factory for a destination that is enabled but not logged in."""
    return None


def config_with(username: str = "grndpagaming", twitch: bool = False, youtube: bool = False):
    """Settings with the given TikTok user and destinations."""
    config = AppConfig()
    config.tiktok.username = username
    config.twitch.enabled = twitch
    config.youtube.enabled = youtube
    return config


def test_source_uses_username_and_saved_euler_key() -> None:
    """The TikTok source gets the clean username and the stored API key."""
    store = MemoryStore()
    store.set(TIKTOK_EULER_KEY, "euler-123")
    source = build_source(config_with("@grndpagaming"), store)
    assert isinstance(source, TikTokSource)
    assert source.username == "grndpagaming"
    assert source._euler_key == "euler-123"


def test_source_without_saved_key() -> None:
    """Without a saved key, the free tier is used."""
    source = build_source(config_with(), MemoryStore())
    assert isinstance(source, TikTokSource)
    assert source._euler_key is None


def test_missing_username_is_a_problem() -> None:
    """An empty TikTok username stops the assembly with a clear problem."""
    factories = {"twitch": console_factory("twitch")}
    with pytest.raises(SetupError) as error:
        assemble_engine(config_with("", twitch=True), MemoryStore(), factories)
    assert error.value.problems == ["Enter the TikTok username of the LIVE to relay."]


def test_no_destination_chosen() -> None:
    """At least one destination must be enabled."""
    with pytest.raises(SetupError) as error:
        assemble_engine(config_with(), MemoryStore(), {})
    assert "Choose at least one destination" in error.value.problems[0]


def test_all_problems_are_reported_together() -> None:
    """Missing username and missing destination are both listed."""
    with pytest.raises(SetupError) as error:
        assemble_engine(config_with(""), MemoryStore(), {})
    assert len(error.value.problems) == 2


def test_enabled_but_not_set_up_destination() -> None:
    """A destination that is enabled but not ready is named in the problem."""
    with pytest.raises(SetupError) as error:
        assemble_engine(config_with(twitch=True), MemoryStore(), {"twitch": not_set_up})
    assert error.value.problems == ["twitch is enabled but not set up yet"]


def test_only_enabled_and_configured_destinations_are_built() -> None:
    """Disabled destinations are skipped; not-ready ones are noted, not fatal."""
    factories = {"twitch": console_factory("twitch"), "youtube": not_set_up}
    setups, skipped = build_destinations(
        config_with(twitch=True, youtube=True), MemoryStore(), factories
    )
    assert [s.destination.name for s in setups] == ["twitch"]
    assert skipped == ["youtube is enabled but not set up yet"]


def test_destination_options_come_from_settings() -> None:
    """Toggles, templates and compact mode follow each destination's settings."""
    config = config_with(twitch=True, youtube=True)
    config.twitch.templates = {"chat": "{user}: {message}"}
    factories = {"twitch": console_factory("twitch"), "youtube": console_factory("youtube")}
    setups, _ = build_destinations(config, MemoryStore(), factories)
    twitch, youtube = setups
    assert twitch.templates == {"chat": "{user}: {message}"}
    assert twitch.compact_mode is False
    assert youtube.compact_mode is True
    assert youtube.toggles["like"] is False  # YouTube default saves quota


def test_assemble_engine_success() -> None:
    """With a source and a ready destination, an engine is returned."""
    factories = {"twitch": console_factory("twitch")}
    assembly = assemble_engine(
        config_with(twitch=True), MemoryStore(), factories, source=ListSource([])
    )
    assert isinstance(assembly.engine, RelayEngine)
    assert assembly.skipped == []


def test_route_options_from_config() -> None:
    """Reload options exist for both destinations."""
    options = route_options_from_config(AppConfig())
    assert set(options) == {"twitch", "youtube"}
    assert options["youtube"].compact_mode is True
