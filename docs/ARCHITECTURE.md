# StreamBridge architecture

This page explains how StreamBridge is put together, for contributors and for
anyone who wants to understand what happens to a TikTok message on its way to
Twitch or YouTube.

## The big picture

```
 TikTok LIVE                                                     Twitch chat
     │                                                                ▲
     ▼                                                                │
┌──────────┐   RelayEvent   ┌─────────────────────────────┐   text   ┌──────────────┐
│  Source  │ ─────────────► │          Pipeline           │ ───────► │ Destination  │
│ (TikTok) │                │ filter → de-dup → gifts →   │  queue   │  (Twitch)    │
└──────────┘                │ route → format → queue      │ + rate   └──────────────┘
                            │                             │  limit   ┌──────────────┐
                            │                             │ ───────► │ Destination  │
                            └─────────────────────────────┘          │  (YouTube)   │
                                         ▲                           └──────────────┘
                                         │ start / stop / reload / test message
                                  ┌──────────────┐        status, counters, feed
                                  │ RelayEngine  │ ───────────────────────────────► UI / CLI
                                  └──────────────┘
```

Everything runs on the user's PC. There is no StreamBridge server.

## Threads

- **The engine runs in its own thread with its own asyncio event loop**
  (`core/engine.py`). The UI thread never does network work, so the window
  never freezes.
- The UI or CLI controls the engine only through thread-safe methods:
  `start()`, `stop()`, `send_test_message()` and `reload_config()`.
- The engine reports back through an `EngineListener` whose methods are called
  **from the engine thread**. The desktop UI turns them into Qt signals.

## A message's journey

Example: a viewer called Budi sends three Roses on TikTok.

1. **Source** (`sources/tiktok.py`) receives TikTokLive events and turns them
   into a `RelayEvent` (`core/events.py`). Gift taps are ignored until the
   streak ends, so this arrives as one event: gift *Rose*, count 3.
2. **Chat filter** (`core/filters.py`) works on chat text only: it lightly
   censors rude words, drops spam and repeated messages, and replaces links
   with a notice. Viewer names are censored for every kind of event.
3. **De-dup** (`core/likes.py`) relays only a viewer's first like per session
   and ignores repeated shares and reposts within 60 seconds.
4. **Gift merger** (`core/gifts.py`) sums the same gift from the same viewer
   within a short window (default 5 s), so a combo becomes one "x3" message.
5. **Routing** (`core/pipeline.py`) sends the event to every destination
   whose event toggles allow it.
6. **Formatting** (`core/formatter.py`) fills the destination's template in
   the relay language (`core/i18n.py`, `resources/i18n/*.json`) and cuts it
   to the platform limit (Twitch 500, YouTube 200 characters). For YouTube,
   chat can first be joined into one message (`core/batching.py`).
7. **Queue** (`core/outqueue.py`): gifts, follows, shares and reposts go
   before chat and likes. Twitch's queue never drops anything; YouTube's keeps
   at most 30 and drops the oldest chat or like.
8. **Rate limiter** (`core/ratelimit.py`) never sends more than the platform
   allows in *any* time window (sliding window, plus a 50 ms safety margin).
9. **Destination** (`destinations/twitch.py`) sends the text. Temporary
   problems (no internet, 429, 5xx) are retried until they work; refusals
   (for example AutoMod) are counted and reported, not retried.

## Packages

| Package | What lives there |
|---|---|
| `core/` | Everything platform-independent: events, filters, queues, rate limits, the engine, settings (`config.py`), secrets (`secrets.py`), and `assembly.py`, which builds an engine from the user's settings |
| `sources/` | Where events come from. `base.Source` is the interface; `tiktok.py` is the real one |
| `destinations/` | Where messages go. `base.Destination` is the interface; `console.py` (for development) and `twitch.py` |
| `auth/` | Logins: `twitch_device.py` (Twitch device code flow, refresh, hourly validation) |
| `ui/` | The desktop app (PySide6 + QML), added in a later phase |
| `tools/` | `cli.py` runs the engine without the UI; `fake_source.py` simulates a LIVE |

## Settings and secrets

- **Settings** are in `%APPDATA%\StreamBridge\config.json` (`core/config.py`).
  Loading is forgiving: unknown keys are ignored and wrong values fall back to
  defaults. The file never contains tokens.
- **Secrets** (Twitch logins, the Euler API key) are in the **Windows
  Credential Manager** through `keyring` (`core/secrets.py`). They are never
  written to settings or log files.
- **Logs** are in `%LOCALAPPDATA%\StreamBridge\logs\` (rotating, 1 MB × 5).

## Rules that keep the relay robust

- Each destination has its own queue, rate limiter and worker. If one
  destination fails to start or breaks, the others keep working.
- Destinations are created only when they are **enabled and configured**
  (`core/assembly.py`); problems are reported to the user all at once.
- On Stop, gifts still being merged and chat still being batched are flushed.
  High-priority messages get up to 5 seconds to go out; anything still waiting
  is counted as "not sent (stopped)", never lost silently.
- The TikTok source reconnects by itself: it re-checks every 90 seconds while
  the streamer is offline and backs off 5 → 10 → 30 → 60 seconds after errors.

## Adding a new destination

1. Subclass `destinations.base.Destination`: set `name`, `max_length`,
   `rate_rules` and `max_queue_size`, and implement `send()` (plus `start()`
   and `stop()` if needed).
2. Raise `TemporarySendError` for problems worth retrying; return
   `SendResult(ok=False, reason=...)` for refusals.
3. Register a factory for it in the engine assembly so it is created from the
   user's settings.
4. Test it against a fake server (see `tests/test_twitch_destination.py`,
   which uses `httpx.MockTransport`) — tests never use the network.

## Testing

- `pytest` runs everything; CI runs the same checks on Windows for every push.
- Time-dependent code takes an injectable clock or sleep function, so tests
  can "jump" minutes ahead without waiting.
- Platform code is tested against fakes: a fake TikTokLive client, a fake
  Twitch server, and an in-memory secret store.
