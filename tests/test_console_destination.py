"""Tests for the development console destination."""

from __future__ import annotations

import asyncio
import io

from streambridge.destinations.console import ConsoleDestination


def _send(text: str, encoding: str) -> str:
    """Send one message to a stream with the given encoding and return what was printed."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding=encoding)
    destination = ConsoleDestination("twitch-sim", stream=stream)
    result = asyncio.run(destination.send(text))
    stream.flush()
    assert result.ok
    return raw.getvalue().decode(encoding)


def test_emoji_do_not_crash_a_cp1252_console() -> None:
    """A Windows console that cannot show emoji prints '?' instead of failing the send."""
    printed = _send("\U0001f4ac hello ⭐", "cp1252")
    assert "hello" in printed
    assert "?" in printed


def test_emoji_are_kept_on_a_utf8_stream() -> None:
    """A stream that can show emoji gets them unchanged."""
    assert "\U0001f4ac" in _send("\U0001f4ac hello", "utf-8")
