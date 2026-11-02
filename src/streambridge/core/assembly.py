"""Build a ready-to-start RelayEngine from the user's settings.

The UI (and the CLI) call ``assemble_engine``: it reads ``AppConfig`` and the
secret store, creates the TikTok source and every destination that is
**enabled and configured**, and reports clear problems instead of starting a
half-working relay.

Destinations are created by *factories*, one per destination name. A factory
returns ``None`` when its destination is enabled but not set up yet (for
example, not logged in); that becomes a problem the user can fix.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from streambridge.core.config import AppConfig, TwitchSettings, YouTubeSettings
from streambridge.core.engine import (
    DestinationSetup,
    EngineListener,
    EngineSettings,
    RelayEngine,
    RouteOptions,
)
from streambridge.core.secrets import TIKTOK_EULER_KEY, SecretStore
from streambridge.destinations.base import Destination
from streambridge.sources.base import Source
from streambridge.sources.tiktok import TikTokSource, clean_username

# Creates the destination for one platform, or returns None if it is not set up.
DestinationFactory = Callable[[AppConfig, SecretStore], Destination | None]

DestinationSettings = TwitchSettings | YouTubeSettings


class SetupError(Exception):
    """The relay cannot start yet; ``problems`` says what the user must fix."""

    def __init__(self, problems: list[str]) -> None:
        """Create the error from a list of user-facing problems."""
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Assembly:
    """A built engine plus notes about destinations that were left out."""

    engine: RelayEngine
    skipped: list[str]


def destination_settings(config: AppConfig) -> dict[str, DestinationSettings]:
    """The settings section of every destination, by name."""
    return {"twitch": config.twitch, "youtube": config.youtube}


def route_options(settings: DestinationSettings) -> RouteOptions:
    """Pipeline options (toggles, templates, compact mode) for one destination."""
    compact = settings.compact_mode if isinstance(settings, YouTubeSettings) else False
    return RouteOptions(
        toggles=settings.events.as_dict(),
        templates=dict(settings.templates),
        compact_mode=compact,
    )


def route_options_from_config(config: AppConfig) -> dict[str, RouteOptions]:
    """Route options for every destination, by name (used for reload)."""
    return {name: route_options(s) for name, s in destination_settings(config).items()}


def euler_key(store: SecretStore) -> str | None:
    """The saved Euler Stream API key, if any."""
    return store.get(TIKTOK_EULER_KEY) or None


def build_source(config: AppConfig, store: SecretStore) -> Source:
    """The TikTok source for the configured username. Raises SetupError if missing."""
    username = clean_username(config.tiktok.username)
    if not username:
        raise SetupError(["Enter the TikTok username of the LIVE to relay."])
    return TikTokSource(username, euler_key=euler_key(store))


def build_destinations(
    config: AppConfig,
    store: SecretStore,
    factories: Mapping[str, DestinationFactory],
) -> tuple[list[DestinationSetup], list[str]]:
    """Create every enabled and configured destination.

    Returns:
        The destination setups, and notes about enabled destinations that could
        not be created (no factory yet, or not set up).
    """
    setups: list[DestinationSetup] = []
    skipped: list[str] = []
    for name, settings in destination_settings(config).items():
        if not settings.enabled:
            continue
        factory = factories.get(name)
        destination = factory(config, store) if factory else None
        if destination is None:
            skipped.append(f"{name} is enabled but not set up yet")
            continue
        options = route_options(settings)
        setups.append(
            DestinationSetup(
                destination,
                options.toggles,
                options.templates,
                compact_mode=options.compact_mode,
            )
        )
    return setups, skipped


def assemble_engine(
    config: AppConfig,
    store: SecretStore,
    factories: Mapping[str, DestinationFactory],
    listener: EngineListener | None = None,
    source: Source | None = None,
) -> Assembly:
    """Build the engine from settings, or raise SetupError listing every problem.

    Args:
        config: The user's settings.
        store: Secret store (logins, API keys).
        factories: Destination factories by name (``"twitch"``, ``"youtube"``).
        listener: Receives engine updates (the UI or the CLI).
        source: Use this source instead of the configured TikTok one (development).
    """
    problems: list[str] = []
    if source is None:
        try:
            source = build_source(config, store)
        except SetupError as error:
            problems.extend(error.problems)

    setups, skipped = build_destinations(config, store, factories)
    if not setups:
        if not any(s.enabled for s in destination_settings(config).values()):
            problems.append("Choose at least one destination (Twitch or YouTube).")
        else:
            problems.extend(skipped)

    if problems or source is None:
        raise SetupError(problems)
    engine = RelayEngine(source, setups, EngineSettings.from_config(config), listener)
    return Assembly(engine=engine, skipped=skipped)
