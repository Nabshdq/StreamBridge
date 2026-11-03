"""Start the Qt application: window, fonts, engine bridge."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from streambridge.core import paths
from streambridge.core.assembly import assemble_engine
from streambridge.core.config import load_config
from streambridge.core.engine import DestinationSetup, EngineListener, EngineSettings, RelayEngine
from streambridge.core.formatter import TWITCH_MAX_LENGTH, YOUTUBE_MAX_LENGTH
from streambridge.core.logging_setup import setup_logging
from streambridge.core.outqueue import YOUTUBE_MAX_QUEUE
from streambridge.core.ratelimit import TWITCH_RULES, YOUTUBE_RULES
from streambridge.core.secrets import KeyringStore
from streambridge.destinations.console import ConsoleDestination
from streambridge.ui.bridge import SOURCE_ID, Backend, EngineFactory
from streambridge.ui.icons import IconProvider

QML_DIR = Path(__file__).resolve().parent / "ui" / "qml"
FAKE_CONNECTIONS = (SOURCE_ID, "twitch-sim", "youtube-sim")


def fake_engine_factory() -> EngineFactory:
    """Engine factory for ``--fake``: simulated events into two console destinations."""
    config = load_config()

    def build(listener: EngineListener) -> RelayEngine:
        # tools/ is a development folder, not part of the installed package.
        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from fake_source import FakeSource

        twitch = ConsoleDestination(
            "twitch-sim", TWITCH_MAX_LENGTH, TWITCH_RULES, max_queue_size=None
        )
        youtube = ConsoleDestination(
            "youtube-sim", YOUTUBE_MAX_LENGTH, YOUTUBE_RULES, max_queue_size=YOUTUBE_MAX_QUEUE
        )
        setups = [
            DestinationSetup(twitch, config.twitch.events.as_dict(), config.twitch.templates),
            DestinationSetup(
                youtube,
                config.youtube.events.as_dict(),
                config.youtube.templates,
                compact_mode=config.youtube.compact_mode,
            ),
        ]
        return RelayEngine(
            FakeSource(interval=0.5), setups, EngineSettings.from_config(config), listener
        )

    return build


def real_engine_factory() -> EngineFactory:
    """Engine factory for the real app: settings from ``config.json``, secrets from keyring.

    Destination factories are added when the Twitch and YouTube destinations are wired in.
    """
    store = KeyringStore()

    def build(listener: EngineListener) -> RelayEngine:
        config = load_config()  # re-read on every Start so Settings changes apply
        return assemble_engine(config, store, {}, listener).engine

    return build


def register_fonts() -> None:
    """Load the bundled Inter font files so the UI looks the same on every PC."""
    for font_file in sorted((paths.resources_dir() / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(font_file))


def run(argv: Sequence[str] | None = None) -> int:
    """Open the window and run until it is closed. Returns the exit code."""
    args = list(sys.argv if argv is None else argv)
    fake = "--fake" in args
    setup_logging()

    # The native Windows style cannot be restyled; "Basic" lets Theme.qml control the look.
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(args)
    app.setApplicationName("StreamBridge")
    register_fonts()

    if fake:
        backend = Backend(fake_engine_factory(), FAKE_CONNECTIONS)
    else:
        config = load_config()
        ids = [SOURCE_ID]
        ids += [n for n, s in (("twitch", config.twitch), ("youtube", config.youtube)) if s.enabled]
        backend = Backend(real_engine_factory(), ids)
    app.aboutToQuit.connect(backend.shutdown)

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    context = engine.rootContext()
    context.setContextProperty("backend", backend)
    engine.addImageProvider("icons", IconProvider(paths.resources_dir() / "icons"))
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        return 1
    exit_code = app.exec()
    # Destroy the QML engine first. Otherwise Python frees ``backend`` while the
    # screens still read it, and QML prints "Cannot read property ... of null".
    del context, engine
    return exit_code
