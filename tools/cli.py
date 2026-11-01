"""Run the relay engine without the UI (development tool).

Examples::

    python tools/cli.py --fake
    python tools/cli.py --fake --lang id --duration 30
    python tools/cli.py --fake --interval 0.05    # flood: watch the rate limit

``--fake`` relays simulated TikTok events to two console destinations that
behave like Twitch (500 characters, 80 messages / 30 s, never drops) and
YouTube (200 characters, compact mode, queue of 30).
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from fake_source import FakeSource
from streambridge.core.config import AppConfig, load_config
from streambridge.core.engine import DestinationSetup, EngineListener, EngineSettings, RelayEngine
from streambridge.core.events import ConnectionStatus
from streambridge.core.formatter import TWITCH_MAX_LENGTH, YOUTUBE_MAX_LENGTH
from streambridge.core.logging_setup import setup_logging
from streambridge.core.outqueue import YOUTUBE_MAX_QUEUE
from streambridge.core.pipeline import Counters
from streambridge.core.ratelimit import TWITCH_RULES, YOUTUBE_RULES
from streambridge.destinations.console import ConsoleDestination


class PrintingListener(EngineListener):
    """Prints status changes and problems to stderr; keeps the latest counters."""

    def __init__(self) -> None:
        """Start with no counters."""
        self.counters: Counters | None = None

    def on_source_status(self, status: ConnectionStatus, detail: str) -> None:
        """Show the source status."""
        print(f"[status] source: {status.value} {detail}".rstrip(), file=sys.stderr)

    def on_destination_status(self, name: str, status: ConnectionStatus, detail: str) -> None:
        """Show a destination status."""
        print(f"[status] {name}: {status.value} {detail}".rstrip(), file=sys.stderr)

    def on_message_rejected(self, destination: str, text: str, reason: str) -> None:
        """Show a refused message."""
        print(f"[refused] {destination} ({reason}): {text}", file=sys.stderr)

    def on_error(self, where: str, message: str) -> None:
        """Show an error."""
        print(f"[error] {where}: {message}", file=sys.stderr)

    def on_counters(self, counters: Counters) -> None:
        """Remember the latest counters."""
        self.counters = counters


def build_parser() -> argparse.ArgumentParser:
    """Command-line options."""
    parser = argparse.ArgumentParser(description="Run StreamBridge without the UI.")
    parser.add_argument("--fake", action="store_true", help="use simulated TikTok events")
    parser.add_argument("--lang", choices=("auto", "en", "id"), help="language of relayed text")
    parser.add_argument(
        "--duration", type=float, default=None, help="stop after N seconds (default: Ctrl+C)"
    )
    parser.add_argument(
        "--interval", type=float, default=0.5, help="seconds between fake events (default 0.5)"
    )
    parser.add_argument("--seed", type=int, default=None, help="random seed for --fake")
    parser.add_argument("--config", type=Path, default=None, help="settings file to read")
    return parser


def build_destinations(config: AppConfig) -> list[DestinationSetup]:
    """Two console destinations that simulate Twitch and YouTube."""
    twitch = ConsoleDestination("twitch-sim", TWITCH_MAX_LENGTH, TWITCH_RULES, max_queue_size=None)
    youtube = ConsoleDestination(
        "youtube-sim", YOUTUBE_MAX_LENGTH, YOUTUBE_RULES, max_queue_size=YOUTUBE_MAX_QUEUE
    )
    return [
        DestinationSetup(twitch, config.twitch.events.as_dict(), config.twitch.templates),
        DestinationSetup(
            youtube,
            config.youtube.events.as_dict(),
            config.youtube.templates,
            compact_mode=config.youtube.compact_mode,
        ),
    ]


def print_summary(counters: Counters | None) -> None:
    """Print the final counters."""
    if counters is None:
        return
    print("\n--- summary ---", file=sys.stderr)
    for name, sent in counters.sent.items():
        print(
            f"{name}: sent {sent}, dropped {counters.dropped.get(name, 0)}, "
            f"refused {counters.rejected.get(name, 0)}",
            file=sys.stderr,
        )
    print(f"filtered (spam): {counters.filtered}", file=sys.stderr)
    print(f"not sent (stopped): {counters.unsent_on_stop}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    if not args.fake:
        build_parser().error("choose a source: --fake (real TikTok comes in Phase 2)")

    # Emoji must not crash the program when output is redirected to a file.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    setup_logging(console_level=logging.WARNING)

    config = load_config(args.config)
    if args.lang:
        config.relay_language = args.lang
    listener = PrintingListener()
    engine = RelayEngine(
        source=FakeSource(interval=args.interval, seed=args.seed),
        destinations=build_destinations(config),
        settings=EngineSettings.from_config(config),
        listener=listener,
    )

    engine.start()
    started = time.monotonic()
    try:
        while engine.is_running:
            if args.duration is not None and time.monotonic() - started >= args.duration:
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nStopping...", file=sys.stderr)
    engine.stop()
    print_summary(listener.counters)
    return 0


if __name__ == "__main__":
    sys.exit(main())
