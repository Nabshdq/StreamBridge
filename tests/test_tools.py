"""Tests for the fake source and the CLI."""

from pathlib import Path

import pytest

import cli
from fake_source import FakeSource
from streambridge.auth import twitch_device
from streambridge.core import paths
from streambridge.core.config import AppConfig
from streambridge.core.secrets import (
    TIKTOK_EULER_KEY,
    TWITCH_BOT_KEY,
    TWITCH_BROADCASTER_KEY,
    YOUTUBE_TOKEN_KEY,
    MemoryStore,
)
from streambridge.destinations.console import ConsoleDestination
from streambridge.destinations.twitch import TwitchDestination
from streambridge.sources.tiktok import TikTokSource


def test_fake_source_is_repeatable_with_seed() -> None:
    """The same seed gives the same events."""
    source_a, source_b = FakeSource(seed=7), FakeSource(seed=7)
    events_a = [source_a.next_event() for _ in range(50)]
    events_b = [source_b.next_event() for _ in range(50)]
    assert [(e.kind, e.user, e.text) for e in events_a] == [
        (e.kind, e.user, e.text) for e in events_b
    ]


def test_fake_source_produces_every_kind() -> None:
    """Over many events, all six kinds appear."""
    source = FakeSource(seed=1)
    kinds = {source.next_event().kind for _ in range(500)}
    assert kinds == {"chat", "gift", "follow", "like", "share", "repost"}


def test_cli_requires_a_source() -> None:
    """Without --fake the CLI explains what to do."""
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_rejects_two_sources() -> None:
    """--fake and --tiktok cannot be used together."""
    with pytest.raises(SystemExit):
        cli.main(["--fake", "--tiktok", "someone"])


def test_cli_builds_tiktok_source() -> None:
    """--tiktok creates a TikTok source with a clean username and the optional key."""
    args = cli.build_parser().parse_args(
        ["--tiktok", "@grndpagaming", "--euler-key", "k", "--show-raw"]
    )
    source = cli.build_source(args)
    assert isinstance(source, TikTokSource)
    assert source.username == "grndpagaming"
    assert source._euler_key == "k"
    assert source._raw_listener is cli.print_raw


def test_cli_builds_fake_source() -> None:
    """--fake still creates the simulated source."""
    args = cli.build_parser().parse_args(["--fake", "--seed", "1"])
    assert isinstance(cli.build_source(args), FakeSource)


def test_print_raw(capsys: pytest.CaptureFixture[str]) -> None:
    """Raw social data is printed on one line to stderr."""
    cli.print_raw({"key": "pm_mt_guidance_share", "share_type": 1})
    assert "[raw] key='pm_mt_guidance_share' share_type=1" in capsys.readouterr().err


@pytest.fixture
def no_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate the Twitch app not being registered yet."""
    monkeypatch.setattr(twitch_device, "TWITCH_CLIENT_ID", "")
    monkeypatch.delenv(twitch_device.CLIENT_ID_ENV, raising=False)


@pytest.fixture
def memory_keyring(monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    """Keep the CLI away from the real Windows Credential Manager."""
    store = MemoryStore()
    monkeypatch.setattr(cli, "KeyringStore", lambda: store)
    return store


def test_twitch_logout_forgets_both_logins(memory_keyring: MemoryStore) -> None:
    """--twitch-logout removes the streamer and bot logins."""
    memory_keyring.set(TWITCH_BROADCASTER_KEY, "x")
    memory_keyring.set(TWITCH_BOT_KEY, "y")
    assert cli.main(["--twitch-logout"]) == 0
    assert memory_keyring.values == {}


def test_twitch_login_without_app_explains(
    no_client_id: None, memory_keyring: MemoryStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """Logging in before the Twitch app exists fails with a clear message."""
    assert cli.main(["--twitch-login"]) == 1
    assert "not registered yet" in capsys.readouterr().err


def test_relay_to_twitch_without_app_explains(
    no_client_id: None, memory_keyring: MemoryStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """--twitch without a client ID stops before starting the engine."""
    assert cli.main(["--fake", "--twitch"]) == 1
    assert "not registered yet" in capsys.readouterr().err


def test_twitch_channel_needs_twitch() -> None:
    """--twitch-channel alone is a usage error."""
    with pytest.raises(SystemExit):
        cli.main(["--fake", "--twitch-channel", "streamer"])


@pytest.mark.parametrize(
    ("extra", "bot_mode"), [([], False), (["--twitch-channel", "@Streamer"], True)]
)
def test_build_twitch_destination_modes(
    monkeypatch: pytest.MonkeyPatch, extra: list[str], bot_mode: bool
) -> None:
    """A channel name switches to bot mode (with the bot login)."""
    monkeypatch.setenv(twitch_device.CLIENT_ID_ENV, "dev-client")
    args = cli.build_parser().parse_args(["--fake", "--twitch", *extra])
    destination = cli.build_twitch_destination(args, MemoryStore())
    assert isinstance(destination, TwitchDestination)
    assert destination._bot_mode is bot_mode
    assert destination._account_key == (TWITCH_BOT_KEY if bot_mode else TWITCH_BROADCASTER_KEY)


def test_save_and_forget_euler_key(
    memory_keyring: MemoryStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Euler key can be saved and removed, and is never printed."""
    assert cli.main(["--save-euler-key", "secret-euler"]) == 0
    assert memory_keyring.get(TIKTOK_EULER_KEY) == "secret-euler"
    assert "secret-euler" not in capsys.readouterr().err
    assert cli.main(["--forget-euler-key"]) == 0
    assert memory_keyring.get(TIKTOK_EULER_KEY) is None


def test_tiktok_uses_saved_euler_key_unless_overridden() -> None:
    """--tiktok picks up the saved key; --euler-key wins for one run."""
    store = MemoryStore()
    store.set(TIKTOK_EULER_KEY, "saved")
    saved = cli.build_source(cli.build_parser().parse_args(["--tiktok", "x"]), store)
    once = cli.build_source(
        cli.build_parser().parse_args(["--tiktok", "x", "--euler-key", "once"]), store
    )
    assert isinstance(saved, TikTokSource)
    assert isinstance(once, TikTokSource)
    assert saved._euler_key == "saved"
    assert once._euler_key == "once"


def test_cli_fake_run_prints_messages(tmp_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A short fake run prints relayed messages for both simulated destinations."""
    exit_code = cli.main(["--fake", "--duration", "1.5", "--interval", "0.02", "--seed", "3"])
    output = capsys.readouterr()
    assert exit_code == 0
    assert "[twitch-sim]" in output.out
    assert "[youtube-sim]" in output.out
    assert "--- summary ---" in output.err


def test_cli_refuses_to_run_without_resources(
    tmp_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A broken install stops the CLI with exit code 2 and a message on stderr."""
    monkeypatch.setattr(paths, "resources_dir", lambda: tmp_path / "no-resources")
    exit_code = cli.main(["--fake", "--duration", "0.1"])
    assert exit_code == 2
    assert "icons/play.svg" in capsys.readouterr().err


def test_youtube_logout_forgets_the_login(memory_keyring: MemoryStore) -> None:
    memory_keyring.set(YOUTUBE_TOKEN_KEY, "x")
    assert cli.main(["--youtube-logout"]) == 0
    assert memory_keyring.values == {}


def test_youtube_import_secret_copies_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memory_keyring: MemoryStore
) -> None:
    monkeypatch.setenv("STREAMBRIDGE_HOME", str(tmp_path / "app"))
    source = tmp_path / "client_secret_123.json"
    source.write_text('{"installed": {"client_id": "abc"}}', encoding="utf-8")
    assert cli.main(["--youtube-import-secret", str(source)]) == 0
    assert (tmp_path / "app" / "client_secret.json").is_file()


def test_youtube_import_secret_rejects_a_web_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memory_keyring: MemoryStore, capsys
) -> None:
    monkeypatch.setenv("STREAMBRIDGE_HOME", str(tmp_path / "app"))
    source = tmp_path / "web.json"
    source.write_text('{"web": {"client_id": "abc"}}', encoding="utf-8")
    assert cli.main(["--youtube-import-secret", str(source)]) == 1
    assert "Desktop app" in capsys.readouterr().err


def test_relay_to_youtube_before_setup_explains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memory_keyring: MemoryStore, capsys
) -> None:
    monkeypatch.setenv("STREAMBRIDGE_HOME", str(tmp_path))
    assert cli.main(["--fake", "--youtube"]) == 1
    assert "not set up" in capsys.readouterr().err


def test_a_real_youtube_destination_replaces_the_simulated_one() -> None:
    real = ConsoleDestination("youtube")
    setups = cli.build_destinations(AppConfig(), youtube_destination=real)
    assert [s.destination.name for s in setups] == ["twitch-sim", "youtube"]
