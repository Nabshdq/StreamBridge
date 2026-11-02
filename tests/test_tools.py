"""Tests for the fake source and the CLI."""

from pathlib import Path

import pytest

import cli
from fake_source import FakeSource
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


def test_cli_fake_run_prints_messages(tmp_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A short fake run prints relayed messages for both simulated destinations."""
    exit_code = cli.main(["--fake", "--duration", "1.5", "--interval", "0.02", "--seed", "3"])
    output = capsys.readouterr()
    assert exit_code == 0
    assert "[twitch-sim]" in output.out
    assert "[youtube-sim]" in output.out
    assert "--- summary ---" in output.err
