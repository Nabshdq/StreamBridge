"""RelayEngine: runs the whole relay in its own thread with its own asyncio loop.

The UI (or the CLI) talks to the engine only through these thread-safe methods:
``start()``, ``stop()`` and ``send_test_message()``. The engine reports back
through an ``EngineListener``. Its methods are called **from the engine
thread**; the Qt bridge (Phase 5) turns them into Qt signals.

Each destination has its own queue, rate limiter and worker task, so a slow
or broken destination never blocks the others.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from streambridge.core.batching import DEFAULT_COMPACT_WINDOW, ChatBatcher
from streambridge.core.config import AppConfig
from streambridge.core.events import PRIORITY_HIGH, ConnectionStatus, RelayEvent
from streambridge.core.filters import (
    DEFAULT_DUPLICATE_WINDOW,
    DEFAULT_SPAM_PHRASES,
    MessageFilter,
    build_word_list,
    load_default_profanity,
)
from streambridge.core.formatter import MessageFormatter, default_templates
from streambridge.core.gifts import DEFAULT_GIFT_DELAY, GiftMerger
from streambridge.core.i18n import Translator
from streambridge.core.likes import DEFAULT_SHARE_REPEAT_WINDOW, SocialDeduper
from streambridge.core.outqueue import OutMessage, OutQueue
from streambridge.core.pacing import DEFAULT_LIVE_TARGET
from streambridge.core.pipeline import Counters, Pipeline, Route
from streambridge.core.ratelimit import RateLimiter
from streambridge.destinations.base import Destination, TemporarySendError
from streambridge.sources.base import Source

logger = logging.getLogger(__name__)

# Waits between retries after a temporary send error; the last one repeats.
RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0)

SOURCE_NAME = "source"


@dataclass(frozen=True)
class DestinationSetup:
    """A destination plus the settings the pipeline needs for it.

    Attributes:
        destination: The destination object.
        toggles: ``{kind: enabled}`` event toggles.
        templates: The user's custom templates (missing kinds use the defaults).
        compact_mode: Join chat into batches (YouTube).
    """

    destination: Destination
    toggles: Mapping[str, bool]
    templates: Mapping[str, str] = field(default_factory=dict)
    compact_mode: bool = False


@dataclass(frozen=True)
class RouteOptions:
    """Per-destination pipeline options that can change while the relay runs.

    Attributes:
        toggles: ``{kind: enabled}`` event toggles.
        templates: The user's custom templates.
        compact_mode: Join chat into batches (YouTube).
    """

    toggles: Mapping[str, bool]
    templates: Mapping[str, str] = field(default_factory=dict)
    compact_mode: bool = False


@dataclass(frozen=True)
class EngineSettings:
    """Settings that are the same for every destination."""

    relay_language: str = "en"
    gift_delay: float = DEFAULT_GIFT_DELAY
    spam_phrases: tuple[str, ...] = DEFAULT_SPAM_PHRASES
    rude_words: tuple[str, ...] = ()
    duplicate_window: float = DEFAULT_DUPLICATE_WINDOW
    share_repeat_window: float = DEFAULT_SHARE_REPEAT_WINDOW
    compact_window: float = DEFAULT_COMPACT_WINDOW
    live_target: float = DEFAULT_LIVE_TARGET
    stop_grace: float = 5.0
    tick_interval: float = 0.25
    counters_interval: float = 1.0

    @classmethod
    def from_config(cls, config: AppConfig) -> "EngineSettings":
        """Build engine settings from the user's settings."""
        rude_words = build_word_list(
            load_default_profanity(),
            config.filters.extra_rude_words,
            config.filters.allowed_words,
        )
        return cls(
            relay_language=config.relay_language,
            gift_delay=config.gift_delay,
            spam_phrases=tuple(config.filters.spam_phrases),
            rude_words=tuple(rude_words),
        )


class EngineListener:
    """Receives engine updates. Override only what you need.

    Every method is called from the engine thread.
    """

    def on_source_status(self, status: ConnectionStatus, detail: str) -> None:
        """The source connection changed."""

    def on_destination_status(self, name: str, status: ConnectionStatus, detail: str) -> None:
        """A destination connection changed."""

    def on_message_sent(self, destination: str, text: str) -> None:
        """A message was accepted by a destination."""

    def on_message_rejected(self, destination: str, text: str, reason: str) -> None:
        """A destination refused a message."""

    def on_error(self, where: str, message: str) -> None:
        """Something went wrong (``where`` is a destination name or ``"source"``)."""

    def on_counters(self, counters: Counters) -> None:
        """New dashboard numbers (a copy, safe to keep)."""

    def on_stopped(self) -> None:
        """The engine has fully stopped."""


@dataclass
class _ActiveDestination:
    """A started destination with its route and limiter.

    ``in_flight`` is the message the worker took from the queue and is
    currently sending (or waiting to send), so it is never lost from the counts.
    """

    setup: DestinationSetup
    route: Route
    limiter: RateLimiter
    in_flight: OutMessage | None = None

    @property
    def name(self) -> str:
        """Destination name."""
        return self.setup.destination.name

    @property
    def unsent_count(self) -> int:
        """Messages not yet sent: queued plus the one in flight."""
        return len(self.route.queue) + (1 if self.in_flight is not None else 0)

    @property
    def has_high_priority_pending(self) -> bool:
        """True while a gift/follow/share/repost/test message is waiting or in flight."""
        in_flight_high = self.in_flight is not None and self.in_flight.priority == PRIORITY_HIGH
        return in_flight_high or self.route.queue.high_priority_count > 0


class RelayEngine:
    """Runs source -> pipeline -> destinations in a background thread."""

    def __init__(
        self,
        source: Source,
        destinations: Sequence[DestinationSetup],
        settings: EngineSettings | None = None,
        listener: EngineListener | None = None,
    ) -> None:
        """Create the engine (nothing runs until ``start()``)."""
        self._source = source
        self._setups = list(destinations)
        self._settings = settings or EngineSettings()
        self._listener = listener or EngineListener()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()
        self._stop_requested: asyncio.Event | None = None
        self._pipeline: Pipeline | None = None
        self._active: list[_ActiveDestination] = []
        self.counters = Counters()

    # --- thread-safe controls ---------------------------------------------

    @property
    def is_running(self) -> bool:
        """True while the engine thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the engine thread. Does nothing if it is already running."""
        if self.is_running:
            return
        self._loop_ready.clear()
        self.counters = Counters()
        self._thread = threading.Thread(target=self._thread_main, name="RelayEngine", daemon=True)
        self._thread.start()
        self._loop_ready.wait(timeout=5)

    def stop(self, wait: bool = True, timeout: float | None = None) -> None:
        """Ask the engine to stop; optionally wait until it has stopped."""
        loop, stop_requested = self._loop, self._stop_requested
        if loop is not None and stop_requested is not None:
            loop.call_soon_threadsafe(stop_requested.set)
        if wait and self._thread is not None:
            self._thread.join(timeout)

    def send_test_message(self, text: str) -> None:
        """Queue a test message for every destination."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._enqueue_test, text)

    def reload_config(self, settings: EngineSettings, routes: Mapping[str, RouteOptions]) -> None:
        """Apply new settings, also while running (thread-safe).

        Changes filters, relay language, templates, event toggles, gift delay
        and compact mode without a restart. Adding or removing a destination
        or changing the TikTok username still needs Stop and Start.

        Args:
            settings: New engine-wide settings.
            routes: New per-destination options, by destination name.
        """
        routes = dict(routes)
        loop = self._loop
        if loop is not None and self.is_running:
            loop.call_soon_threadsafe(self._apply_reload, settings, routes)
        else:
            self._apply_reload(settings, routes)

    # --- engine thread ------------------------------------------------------

    def _thread_main(self) -> None:
        """Body of the engine thread."""
        try:
            asyncio.run(self._run())
        except Exception as error:
            logger.exception("Engine crashed")
            self._notify(self._listener.on_error, "engine", str(error))
        finally:
            self._loop = None
            self._stop_requested = None
            self._loop_ready.set()
            self._notify(self._listener.on_stopped)

    async def _run(self) -> None:
        """Start everything, wait for stop, then shut down cleanly."""
        self._loop = asyncio.get_running_loop()
        self._stop_requested = asyncio.Event()
        self._loop_ready.set()

        translator = Translator(self._settings.relay_language)
        self._active = await self._start_destinations(translator)
        self._pipeline = self._build_pipeline(translator)

        workers = [asyncio.create_task(self._worker(active)) for active in self._active]
        source_task = asyncio.create_task(self._run_source())
        ticker_task = asyncio.create_task(self._ticker())

        await self._stop_requested.wait()
        await self._shutdown(source_task, ticker_task, workers)

    async def _start_destinations(self, translator: Translator) -> list[_ActiveDestination]:
        """Start each destination; a failing one is reported and left out."""
        active = []
        for setup in self._setups:
            destination = setup.destination
            self._notify(
                self._listener.on_destination_status,
                destination.name,
                ConnectionStatus.CONNECTING,
                "",
            )
            try:
                await destination.start()
            except Exception as error:
                logger.exception("Destination %s failed to start", destination.name)
                self._notify(
                    self._listener.on_destination_status,
                    destination.name,
                    ConnectionStatus.ERROR,
                    str(error),
                )
                self._notify(self._listener.on_error, destination.name, str(error))
                continue
            active.append(self._make_active(setup, translator))
            self._notify(
                self._listener.on_destination_status,
                destination.name,
                ConnectionStatus.CONNECTED,
                "",
            )
        return active

    def _make_active(self, setup: DestinationSetup, translator: Translator) -> _ActiveDestination:
        """Create the route and limiter for a started destination."""
        destination = setup.destination
        route = Route(
            name=destination.name,
            toggles=dict(setup.toggles),
            formatter=self._make_formatter(destination, setup.templates, translator),
            queue=OutQueue(destination.max_queue_size),
            batcher=self._make_batcher(destination, translator) if setup.compact_mode else None,
            quota=destination.quota,
            pace_target=self._settings.live_target if destination.quota is not None else 0.0,
        )
        return _ActiveDestination(setup, route, RateLimiter(destination.rate_rules))

    @staticmethod
    def _make_formatter(
        destination: Destination, templates: Mapping[str, str], translator: Translator
    ) -> MessageFormatter:
        """Formatter with the language's default templates and the user's own ones."""
        return MessageFormatter(default_templates(translator), destination.max_length, templates)

    def _make_batcher(self, destination: Destination, translator: Translator) -> ChatBatcher:
        """Compact-mode batcher for a destination."""
        return ChatBatcher(
            prefix=translator.text("relay.compact_prefix"),
            window=self._settings.compact_window,
            max_length=destination.max_length,
            keep_newest=True,
        )

    def _make_filter(self, translator: Translator) -> MessageFilter:
        """Chat filter from the current settings."""
        settings = self._settings
        return MessageFilter(
            spam_phrases=settings.spam_phrases,
            profanity_words=settings.rude_words,
            link_text=translator.text("relay.link_placeholder"),
            duplicate_window=settings.duplicate_window,
        )

    def _build_pipeline(self, translator: Translator) -> Pipeline:
        """Create the pipeline for the started destinations."""
        settings = self._settings
        return Pipeline(
            message_filter=self._make_filter(translator),
            deduper=SocialDeduper(repeat_window=settings.share_repeat_window),
            gift_merger=GiftMerger(delay=settings.gift_delay),
            routes=[active.route for active in self._active],
            counters=self.counters,
        )

    def _apply_reload(self, settings: EngineSettings, routes: dict[str, RouteOptions]) -> None:
        """Apply new settings (runs in the engine thread, or directly when stopped)."""
        self._settings = settings
        self._setups = [self._updated_setup(setup, routes) for setup in self._setups]
        pipeline = self._pipeline
        if pipeline is None:
            return
        translator = Translator(settings.relay_language)
        pipeline.message_filter = self._make_filter(translator)
        pipeline.gift_merger.delay = settings.gift_delay
        pipeline.deduper.repeat_window = settings.share_repeat_window
        for active in self._active:
            active.setup = self._updated_setup(active.setup, routes)
            self._apply_route(active, translator)
        logger.info("Settings reloaded while running")

    @staticmethod
    def _updated_setup(
        setup: DestinationSetup, routes: dict[str, RouteOptions]
    ) -> DestinationSetup:
        """A copy of ``setup`` with new options, if ``routes`` has some for it."""
        options = routes.get(setup.destination.name)
        if options is None:
            return setup
        return replace(
            setup,
            toggles=dict(options.toggles),
            templates=dict(options.templates),
            compact_mode=options.compact_mode,
        )

    def _apply_route(self, active: _ActiveDestination, translator: Translator) -> None:
        """Update one running route from its (new) setup."""
        assert self._pipeline is not None
        setup, route = active.setup, active.route
        destination = setup.destination
        route.toggles = dict(setup.toggles)
        route.formatter = self._make_formatter(destination, setup.templates, translator)
        if setup.compact_mode and route.batcher is None:
            route.batcher = self._make_batcher(destination, translator)
        elif setup.compact_mode and route.batcher is not None:
            # Keep the chat lines already collected; only update the settings.
            route.batcher.prefix = translator.text("relay.compact_prefix")
            route.batcher.window = self._settings.compact_window
        elif route.batcher is not None:
            # Compact mode turned off: send what was collected, then stop batching.
            self._pipeline.flush_batcher(route)
            route.batcher = None

    async def _run_source(self) -> None:
        """Run the source until cancelled; report if it crashes."""
        try:
            await self._source.run(self._on_event, self._on_source_status)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Source %s crashed", self._source.name)
            self._on_source_status(ConnectionStatus.ERROR, str(error))
            self._notify(self._listener.on_error, SOURCE_NAME, str(error))

    def _on_event(self, event: RelayEvent) -> None:
        """Called by the source for every event."""
        if self._pipeline is not None:
            self._pipeline.handle(event, time.time())

    def _on_source_status(self, status: ConnectionStatus, detail: str) -> None:
        """Called by the source when its connection changes."""
        if status == ConnectionStatus.CONNECTED and self._pipeline is not None:
            self._pipeline.reset_session(time.time())
        self._notify(self._listener.on_source_status, status, detail)

    async def _ticker(self) -> None:
        """Release due gifts/batches regularly and report counters."""
        loop = asyncio.get_running_loop()
        last_report = 0.0
        while True:
            if self._pipeline is not None:
                self._pipeline.tick(time.time())
            if loop.time() - last_report >= self._settings.counters_interval:
                self._report_counters()
                last_report = loop.time()
            await asyncio.sleep(self._settings.tick_interval)

    async def _worker(self, active: _ActiveDestination) -> None:
        """Send queued messages for one destination, forever."""
        while True:
            message = await active.route.queue.get()
            active.in_flight = message
            await self._send_with_retry(active, message)
            # Only cleared after a finished attempt: if the task is cancelled
            # while sending, the message still counts as unsent.
            active.in_flight = None

    async def _send_with_retry(self, active: _ActiveDestination, message: OutMessage) -> None:
        """Send one message; retry temporary errors until it works."""
        destination = active.setup.destination
        attempt = 0
        while True:
            await active.limiter.acquire()
            try:
                result = await destination.send(message.text)
            except TemporarySendError as error:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                attempt += 1
                logger.warning("%s: temporary error (%s); retry in %ss", active.name, error, delay)
                self._notify(
                    self._listener.on_destination_status,
                    active.name,
                    ConnectionStatus.DISCONNECTED,
                    str(error),
                )
                await asyncio.sleep(delay)
                continue
            except Exception as error:
                logger.exception("%s: unexpected send error", active.name)
                self.counters.rejected[active.name] += 1
                self._notify(self._listener.on_error, active.name, str(error))
                return

            if attempt > 0:
                self._notify(
                    self._listener.on_destination_status,
                    active.name,
                    ConnectionStatus.CONNECTED,
                    "",
                )
            if result.ok:
                self.counters.sent[active.name] += 1
                self._notify(self._listener.on_message_sent, active.name, message.text)
            else:
                self.counters.rejected[active.name] += 1
                logger.info("%s refused message (%s): %s", active.name, result.reason, message.text)
                self._notify(
                    self._listener.on_message_rejected, active.name, message.text, result.reason
                )
            return

    async def _shutdown(
        self,
        source_task: asyncio.Task[None],
        ticker_task: asyncio.Task[None],
        workers: list[asyncio.Task[None]],
    ) -> None:
        """Stop the source, send held gifts/follows (with a time limit), then stop."""
        for task in (source_task, ticker_task):
            task.cancel()
        await asyncio.gather(source_task, ticker_task, return_exceptions=True)

        if self._pipeline is not None:
            self._pipeline.flush_all(time.time())
        await self._wait_for_high_priority(self._settings.stop_grace)

        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        self.counters.unsent_on_stop = sum(active.unsent_count for active in self._active)
        for active in self._active:
            try:
                await active.setup.destination.stop()
            except Exception:
                logger.exception("Destination %s failed to stop cleanly", active.name)
            self._notify(
                self._listener.on_destination_status,
                active.name,
                ConnectionStatus.STOPPED,
                "",
            )
        self._notify(self._listener.on_source_status, ConnectionStatus.STOPPED, "")
        self._report_counters()
        self._pipeline = None

    async def _wait_for_high_priority(self, grace: float) -> None:
        """Wait until gifts/follows/shares/reposts are sent, at most ``grace`` seconds."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + grace
        while loop.time() < deadline:
            if not any(active.has_high_priority_pending for active in self._active):
                return
            await asyncio.sleep(0.05)

    def _enqueue_test(self, text: str) -> None:
        """Queue a test message (runs in the engine thread)."""
        if self._pipeline is None:
            logger.warning("Test message ignored: engine is not ready")
            return
        self._pipeline.enqueue_text(text)

    def _report_counters(self) -> None:
        """Update waiting counts and send a copy of the counters to the listener."""
        for active in self._active:
            self.counters.waiting[active.name] = active.unsent_count
            quota = active.route.quota
            if quota is not None:
                self.counters.quota_used[active.name] = quota.used
                self.counters.quota_budget = quota.budget
        self._notify(self._listener.on_counters, self.counters.snapshot())

    @staticmethod
    def _notify(callback: Callable[..., None], *args: Any) -> None:
        """Call a listener method; a bug in the listener must not stop the engine."""
        try:
            callback(*args)
        except Exception:
            logger.exception("Engine listener raised an error")
