"""Tests for the fake source and the CLI."""

from pathlib import Path

import pytest

import cli
from fake_source import FakeSource
from streambridge.auth import twitch_device
from streambridge.core.secrets import TWITCH_BOT_KEY, TWITCH_BROADCASTER_KEY, MemoryStore
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


def test_cli_fake_run_prints_messages(tmp_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A short fake run prints relayed messages for both simulated destinations."""
    exit_code = cli.main(["--fake", "--duration", "1.5", "--interval", "0.02", "--seed", "3"])
    output = capsys.readouterr()
    assert exit_code == 0
    assert "[twitch-sim]" in output.out
    assert "[youtube-sim]" in output.out
    assert "--- summary ---" in output.err
