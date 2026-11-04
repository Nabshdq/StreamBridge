"""Run the relay engine without the UI (development tool).

Examples::

    python tools/cli.py --fake
    python tools/cli.py --fake --lang id --duration 30
    python tools/cli.py --fake --interval 0.05    # flood: watch the rate limit
    python tools/cli.py --tiktok @username --lang id
    python tools/cli.py --tiktok @username --show-raw   # print raw follow/share data

    python tools/cli.py --twitch-login                  # log in the streamer account
    python tools/cli.py --twitch-login-bot              # log in a bot account
    python tools/cli.py --twitch-logout                 # forget both logins
    python tools/cli.py --tiktok @username --twitch     # relay to real Twitch chat
    python tools/cli.py --tiktok @username --twitch --twitch-channel streamer  # bot

    python tools/cli.py --youtube-import-secret client_secret.json   # copy your Google file
    python tools/cli.py --youtube-login                 # opens the browser (not yet tested live)
    python tools/cli.py --youtube-logout                # forget the YouTube login
    python tools/cli.py --tiktok @username --youtube    # relay to real YouTube live chat

Events (simulated with ``--fake``, or from a real LIVE with ``--tiktok``) are
relayed to two console destinations that behave like Twitch (500 characters,
80 messages / 30 s, never drops) and YouTube (200 characters, compact mode,
queue of 30). With ``--twitch`` or ``--youtube`` the real chat replaces the simulated one.

``--euler-key`` is only used for one run. ``--save-euler-key KEY`` stores the
key in the Windows Credential Manager so ``--tiktok`` uses it automatically;
``--forget-euler-key`` removes it. Twitch logins are saved there too.
"""

import argparse
import asyncio
import logging
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

import httpx

from fake_source import FakeSource
from streambridge.auth import google_oauth
from streambridge.auth.twitch_device import (
    BOT_SCOPES,
    BROADCASTER_SCOPES,
    DeviceCode,
    TwitchAccount,
    TwitchAuth,
    TwitchAuthError,
    TwitchSetupError,
    get_client_id,
)
from streambridge.core.assembly import euler_key as saved_euler_key
from streambridge.core.config import AppConfig, load_config
from streambridge.core.engine import DestinationSetup, EngineListener, EngineSettings, RelayEngine
from streambridge.core.events import ConnectionStatus
from streambridge.core.formatter import TWITCH_MAX_LENGTH, YOUTUBE_MAX_LENGTH
from streambridge.core.logging_setup import setup_logging
from streambridge.core.outqueue import YOUTUBE_MAX_QUEUE
from streambridge.core.pipeline import Counters
from streambridge.core.ratelimit import TWITCH_RULES, YOUTUBE_RULES
from streambridge.core.secrets import (
    TIKTOK_EULER_KEY,
    TWITCH_BOT_KEY,
    TWITCH_BROADCASTER_KEY,
    KeyringStore,
    SecretStore,
)
from streambridge.core.selfcheck import startup_check
from streambridge.destinations.base import Destination
from streambridge.destinations.console import ConsoleDestination
from streambridge.destinations.twitch import TwitchDestination
from streambridge.destinations.youtube import youtube_factory
from streambridge.sources.base import Source
from streambridge.sources.tiktok import TikTokSource


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
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--fake", action="store_true", help="use simulated TikTok events")
    source.add_argument("--tiktok", metavar="USERNAME", help="read a real TikTok LIVE")
    parser.add_argument(
        "--euler-key", default=None, help="Euler Stream API key for this run only (not saved)"
    )
    euler = parser.add_mutually_exclusive_group()
    euler.add_argument(
        "--save-euler-key", metavar="KEY", help="save an Euler API key in Credential Manager"
    )
    euler.add_argument(
        "--forget-euler-key", action="store_true", help="remove the saved Euler API key"
    )
    parser.add_argument(
        "--show-raw", action="store_true", help="print raw follow/share data (finding reposts)"
    )
    parser.add_argument("--lang", choices=("auto", "en", "id"), help="language of relayed text")
    parser.add_argument(
        "--duration", type=float, default=None, help="stop after N seconds (default: Ctrl+C)"
    )
    parser.add_argument(
        "--interval", type=float, default=0.5, help="seconds between fake events (default 0.5)"
    )
    parser.add_argument("--seed", type=int, default=None, help="random seed for --fake")
    parser.add_argument("--config", type=Path, default=None, help="settings file to read")

    twitch = parser.add_argument_group("Twitch")
    login = twitch.add_mutually_exclusive_group()
    login.add_argument("--twitch-login", action="store_true", help="log in the streamer account")
    login.add_argument("--twitch-login-bot", action="store_true", help="log in a bot account")
    login.add_argument("--twitch-logout", action="store_true", help="forget both Twitch logins")
    twitch.add_argument(
        "--twitch", action="store_true", help="send to the real Twitch chat (not twitch-sim)"
    )
    twitch.add_argument(
        "--twitch-channel",
        metavar="NAME",
        default="",
        help="channel the bot posts to (bot mode; the bot must be a moderator there)",
    )

    youtube = parser.add_argument_group("YouTube")
    yt_command = youtube.add_mutually_exclusive_group()
    yt_command.add_argument(
        "--youtube-import-secret",
        type=Path,
        metavar="PATH",
        help="copy your client_secret.json (Desktop app) into the app folder",
    )
    yt_command.add_argument(
        "--youtube-login", action="store_true", help="log in to Google in the browser"
    )
    yt_command.add_argument(
        "--youtube-logout", action="store_true", help="forget the YouTube login"
    )
    youtube.add_argument(
        "--youtube", action="store_true", help="send to the real YouTube chat (not youtube-sim)"
    )
    return parser


def build_twitch_destination(args: argparse.Namespace, store: SecretStore) -> Destination:
    """The real Twitch destination: streamer mode, or bot mode with --twitch-channel."""
    bot_mode = bool(args.twitch_channel)
    return TwitchDestination(
        client_id=get_client_id(),
        store=store,
        account_key=TWITCH_BOT_KEY if bot_mode else TWITCH_BROADCASTER_KEY,
        channel=args.twitch_channel,
        bot_mode=bot_mode,
    )


def build_destinations(
    config: AppConfig,
    twitch_destination: Destination | None = None,
    youtube_destination: Destination | None = None,
) -> list[DestinationSetup]:
    """Twitch and YouTube, each simulated unless a real one is given."""
    twitch = twitch_destination or ConsoleDestination(
        "twitch-sim", TWITCH_MAX_LENGTH, TWITCH_RULES, max_queue_size=None
    )
    youtube = youtube_destination or ConsoleDestination(
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


def print_raw(raw: dict[str, Any]) -> None:
    """Print raw follow/share data on one line."""
    fields = " ".join(f"{key}={value!r}" for key, value in raw.items())
    print(f"[raw] {fields}", file=sys.stderr)


def build_source(args: argparse.Namespace, store: SecretStore | None = None) -> Source:
    """Create the source chosen on the command line.

    The Euler key comes from ``--euler-key`` (this run only) or else from the
    key saved with ``--save-euler-key``.
    """
    if args.tiktok:
        key = args.euler_key or (saved_euler_key(store) if store is not None else None)
        return TikTokSource(
            args.tiktok,
            euler_key=key,
            raw_listener=print_raw if args.show_raw else None,
        )
    return FakeSource(interval=args.interval, seed=args.seed)


def run_euler_key_command(args: argparse.Namespace, store: SecretStore) -> int:
    """Handle --save-euler-key and --forget-euler-key (the key is never printed)."""
    if args.forget_euler_key:
        store.delete(TIKTOK_EULER_KEY)
        print("Euler API key removed from this PC.", file=sys.stderr)
        return 0
    key = args.save_euler_key.strip()
    if not key:
        print("[error] The Euler API key is empty.", file=sys.stderr)
        return 1
    store.set(TIKTOK_EULER_KEY, key)
    print("Euler API key saved in the Windows Credential Manager.", file=sys.stderr)
    return 0


def show_device_code(device: DeviceCode) -> None:
    """Tell the user how to approve the login, and open the page."""
    print(f"\nOpen {device.verification_uri}", file=sys.stderr)
    print(f"and confirm the code: {device.user_code}", file=sys.stderr)
    print("Waiting for you to click Authorize on Twitch...", file=sys.stderr)
    webbrowser.open(device.verification_uri)


async def twitch_login(client_id: str, store: SecretStore, bot: bool) -> str:
    """Run the Twitch device login and save it. Returns the logged-in name."""
    async with httpx.AsyncClient() as http:
        account = TwitchAccount(
            TwitchAuth(client_id, http), store, TWITCH_BOT_KEY if bot else TWITCH_BROADCASTER_KEY
        )
        tokens = await account.login(BOT_SCOPES if bot else BROADCASTER_SCOPES, show_device_code)
    return tokens.login


def run_twitch_account_command(args: argparse.Namespace, store: SecretStore) -> int:
    """Handle --twitch-login, --twitch-login-bot and --twitch-logout."""
    if args.twitch_logout:
        store.delete(TWITCH_BROADCASTER_KEY)
        store.delete(TWITCH_BOT_KEY)
        print("Twitch logins removed from this PC.", file=sys.stderr)
        return 0
    try:
        login = asyncio.run(twitch_login(get_client_id(), store, bot=args.twitch_login_bot))
    except (TwitchSetupError, TwitchAuthError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    role = "bot" if args.twitch_login_bot else "streamer"
    print(f"Logged in to Twitch as @{login} ({role}). The login is saved.", file=sys.stderr)
    return 0


def run_youtube_account_command(args: argparse.Namespace, store: SecretStore) -> int:
    """Handle --youtube-import-secret, --youtube-login and --youtube-logout."""
    if args.youtube_logout:
        google_oauth.logout(store)
        print("YouTube login removed from this PC.", file=sys.stderr)
        return 0
    try:
        if args.youtube_import_secret is not None:
            google_oauth.import_client_secret(args.youtube_import_secret)
            print("client_secret.json copied into the app folder.", file=sys.stderr)
            return 0
        google_oauth.login(store)
    except google_oauth.YouTubeAuthError as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    print("Logged in to YouTube. The login is saved.", file=sys.stderr)
    return 0


def print_summary(counters: Counters | None) -> None:
    """Print the final counters."""
    if counters is None:
        return
    print("\n--- summary ---", file=sys.stderr)
    for name, sent in counters.sent.items():
        line = (
            f"{name}: sent {sent}, dropped {counters.dropped.get(name, 0)}, "
            f"refused {counters.rejected.get(name, 0)}"
        )
        if name in counters.quota_used:
            line += f", quota {counters.quota_used[name]} / {counters.quota_budget}"
        print(line, file=sys.stderr)
    print(f"filtered (spam): {counters.filtered}", file=sys.stderr)
    print(f"not sent (stopped): {counters.unsent_on_stop}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    youtube_command = bool(
        args.youtube_import_secret is not None or args.youtube_login or args.youtube_logout
    )
    account_command = (
        args.twitch_login or args.twitch_login_bot or args.twitch_logout or youtube_command
    )
    euler_command = args.save_euler_key is not None or args.forget_euler_key
    if not (account_command or euler_command) and not args.fake and not args.tiktok:
        parser.error("choose a source: --fake or --tiktok USERNAME (or a login option)")
    if args.twitch_channel and not args.twitch:
        parser.error("--twitch-channel needs --twitch")

    # Emoji must not crash the program when output is redirected to a file.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    setup_logging(console_level=logging.WARNING)

    store = KeyringStore()
    if euler_command:
        return run_euler_key_command(args, store)
    if youtube_command:
        return run_youtube_account_command(args, store)
    if account_command:
        return run_twitch_account_command(args, store)

    if not startup_check(lambda _title, text: print(text, file=sys.stderr)):
        return 2

    config = load_config(args.config)
    if args.lang:
        config.relay_language = args.lang
    try:
        twitch = build_twitch_destination(args, store) if args.twitch else None
    except TwitchSetupError as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    youtube = None
    if args.youtube:
        youtube = youtube_factory(config, store)
        if youtube is None:
            print(
                "[error] YouTube is not set up. Run --youtube-import-secret PATH, "
                "then --youtube-login.",
                file=sys.stderr,
            )
            return 1
    listener = PrintingListener()
    engine = RelayEngine(
        source=build_source(args, store),
        destinations=build_destinations(config, twitch, youtube),
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
