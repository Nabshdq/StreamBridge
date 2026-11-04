# Progress: StreamBridge
Last updated: 2026-11-04

**Goal:** a Windows app that relays a TikTok LIVE (chat, gifts, follows, likes, shares, reposts) to Twitch and/or YouTube chat.
**Now:** the app window, settings and first-run wizard work in demo mode; real Twitch and YouTube connections are not finished yet.

## Map

- ✅ Phase 0 - Repo setup: done
- ✅ Phase 1 - Core engine (filters, gift merging, queue, formatting): done
- 🟡 Phase 2 - TikTok source: code pushed, not closed (needs a live-end and restart test)
- 🟡 Phase 3 - Twitch destination: code pushed, not closed (needs Twitch app registration, then a real test)
- ⬜ Phase 4 - YouTube destination: not started
- ✅ Phase 5 - UI skeleton: done
- 🔵 Phase 6 - Wizard, Settings, languages: 3 of 4 parts done
  - ✅ 6a Saved settings and runtime screen-language switch · ✅ 6b Settings and About pages · ✅ 6c First-run wizard
  - ⛔ 6d Twitch and YouTube login steps: waiting for Phase 3 and 4
- ⬜ Phase 7 - Packaging and beta: not started
- ⬜ Phase 8 - Fixes from beta feedback: not started

## Last step

- What was done: the first-run wizard (welcome, TikTok username, destination choice, finish) and a "Run the setup again" button in Settings.
- Result: 338 tests pass, lint and formatting are clean, CI is green on `60636da`.
- How to check: `python -m streambridge --fake` opens the app in demo mode.

## Next step

- What comes next: connect the real destinations (Twitch and YouTube), then the login steps in the wizard (6d).
- Why it matters: until then the app can only run in demo mode.
- Needed from the maintainer: Twitch app registration; a Google Cloud project for YouTube; a real LIVE for the final tests.

## Notes

- Phases 2 and 3 stay open until tested against a real LIVE. Code being pushed is not the same as done.
- Phase 4 open decision: YouTube compact mode could use a large share of the daily quota; a pacing choice is needed.

## History

- 2026-11-04: first-run wizard (6c) pushed; CI formatting fix; progress map added.
- 2026-11-03: UI skeleton and Dashboard (Phase 5), saved settings (6a), Settings and About pages (6b).
- 2026-11-02: core engine (Phase 1), TikTok source (Phase 2), Twitch destination code (Phase 3), CI, architecture docs.
- 2026-11-01: repo setup (Phase 0).
