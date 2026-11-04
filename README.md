# StreamBridge

[![CI](https://github.com/Nabshdq/StreamBridge/actions/workflows/ci.yml/badge.svg)](https://github.com/Nabshdq/StreamBridge/actions/workflows/ci.yml)

*Your TikTok viewers, visible on Twitch and YouTube.*

StreamBridge is a Windows desktop app that relays chat, gifts, follows, likes,
shares and reposts from a TikTok LIVE to Twitch chat and/or YouTube live chat.
Everything runs on your own PC, and you use your own accounts.

> **Status:** early development. There is no release yet.

<!-- PROGRESS:START -->
## Progress
*Last updated: 2026-11-04*

**Now:** packaging has started: a test build of the app runs as a Windows program and finds its translations, icons and fonts. The window, settings and first-run wizard work in demo mode, and the YouTube destination is built. **Next:** build the real app (not just a test program), make it smaller, add the update check and the installer. Real tests with TikTok, Twitch and YouTube are still pending.

- ✅ Phase 0 - Repo setup: done
- ✅ Phase 1 - Core engine: done
- 🟡 Phase 2 - TikTok source: code pushed, live-end test pending
- 🟡 Phase 3 - Twitch destination: code pushed, real test pending
- 🟡 Phase 4 - YouTube destination: code pushed (mock-tested, quota shown on the dashboard), real test pending
- ✅ Phase 5 - UI skeleton: done
- 🔵 Phase 6 - Wizard, Settings, languages: 3 of 4 parts done (login steps pending)
- 🔵 Phase 7 - Packaging and beta: in progress (test build runs; installer not started)
- ⬜ Phase 8 - Fixes from beta feedback: not started
<!-- PROGRESS:END -->

## Planned features

- Read a TikTok LIVE anonymously (no TikTok login).
- Send to Twitch, YouTube, or both.
- Light censoring of rude words, spam filtering, and link hiding.
- Gift combo merging and per-destination message templates.
- Built-in rate limiting and YouTube quota tracking.
- English and Bahasa Indonesia, for the app and for relayed messages.

## Requirements

- Windows 10 or 11.

## For developers

You need Python 3.12 and Git.

```powershell
git clone https://github.com/Nabshdq/StreamBridge.git
cd StreamBridge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run the checks (the same ones CI runs on every push):

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe -m pytest
```

Try the relay without the app, using the command-line tool:

```powershell
# Simulated TikTok events, printed as Twitch-like and YouTube-like output
.\.venv\Scripts\python.exe tools\cli.py --fake --lang en

# A real TikTok LIVE (read-only, no login needed)
.\.venv\Scripts\python.exe tools\cli.py --tiktok @username
```

Press Ctrl+C to stop; a summary of sent, dropped and filtered messages follows.
Run `tools\cli.py --help` for all options.

How the pieces fit together is explained in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Project layout:

| Folder | Contents |
|---|---|
| `src/streambridge/core/` | Relay engine: events, filters, queues, rate limits, settings |
| `src/streambridge/sources/` | Where events come from (TikTok) |
| `src/streambridge/destinations/` | Where messages go (console for now; Twitch and YouTube later) |
| `src/streambridge/resources/` | Translations, the default rude-word list, icons and fonts |
| `tools/` | Command-line tool and simulated TikTok source |
| `tests/` | Automated tests (pytest) |

Contributions are welcome. Please keep code, comments and commit messages in
English, add tests for new logic, and make sure the checks above pass.

## License

StreamBridge is free software, licensed under the
[GNU General Public License v3.0 or later](LICENSE).
