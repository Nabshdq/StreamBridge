"""Tests for the fake source and the CLI."""

from pathlib import Path

import pytest

import cli
from fake_source import FakeSource


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


def test_cli_fake_run_prints_messages(tmp_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A short fake run prints relayed messages for both simulated destinations."""
    exit_code = cli.main(["--fake", "--duration", "1.5", "--interval", "0.02", "--seed", "3"])
    output = capsys.readouterr()
    assert exit_code == 0
    assert "[twitch-sim]" in output.out
    assert "[youtube-sim]" in output.out
    assert "--- summary ---" in output.err
