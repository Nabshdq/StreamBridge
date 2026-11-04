---
name: progress-map
description: Update PROGRESS.md (the public phase map of StreamBridge) and show a short progress map in chat. Use when the owner asks for the progress map or "how far are we", and whenever a phase or sub-phase is finished.
---

# Progress map (StreamBridge)

Two outputs, always together:

1. **`PROGRESS.md`** in the repo root: public on GitHub, **in English** (project rule 4).
2. **A short map in chat**, in simple Bahasa Indonesia, so the owner can follow along.

## Facts come only from

- the maintainer's progress notes (session memory `project-progress.md`),
- `git log`, `git ls-remote origin main`,
- the CI runs API: `https://api.github.com/repos/Nabshdq/StreamBridge/actions/runs?head_sha=<HEAD>`,
- test and lint results from the `test-runner` subagent.

Never guess. If something was not checked, write "not checked".

## Phases (from CLAUDE.md section 10)

0 Repo setup · 1 Core engine · 2 TikTok source · 3 Twitch destination ·
4 YouTube destination · 5 UI skeleton · 6 Wizard, Settings, languages
(6a, 6b, 6c, 6d) · 7 Packaging and beta · 8 Fixes from beta feedback.

## Honest statuses (icon plus a word, never an icon alone)

- ✅ Done: finished, checked, owner approved.
- 🟡 Code pushed, not closed: the code exists but the real-world test is missing.
  **Never show this as done.**
- 🔵 In progress.
- ⬜ Not started.
- ⛔ Blocked, with the reason in one short phrase.

## Keep out of the public file

Personal or private material: phone or SMS details, account or login problems,
any content of the local `CLAUDE.md`, and the assistant's own workflow
(advisor, subagents, skills). Write blockers neutrally, for example
"Twitch app registration pending". Do not name accounts, emails or tokens.

## Steps

1. Gather the facts above (run `git log`, the CI API, and read the notes).
2. Rewrite `PROGRESS.md` using the format below. Keep the last 10 history lines.
3. Show the chat map in Bahasa Indonesia: one line for the position, 2-3 simple
   sentences for the last step, 2-3 for the next step, then the phase list with
   word statuses, and say whether `PROGRESS.md` is committed or not.
4. **Do not commit or push without the owner's approval.** When approved: stage
   only the exact path (`git add PROGRESS.md`), use a `docs:` commit, then run
   the `push-verify` skill (including the CI check).
5. Do not edit `README.md` without permission; offering a link to
   `PROGRESS.md` is fine.

## PROGRESS.md format

```
# Progress: StreamBridge
Last updated: <date>

**Goal:** <one sentence>
**Now:** <one sentence>

## Map
- ✅ Phase 0 - Repo setup: done
- 🟡 Phase 2 - TikTok source: code pushed, live-end test pending
- ...

## Last step
- What was done: ...
- Result: ...
- How to check: ...

## Next step
- What comes next: ...
- Why it matters: ...
- Needed from the maintainer: ... (or "nothing")

## Notes
- Open decisions and things not yet checked.

## History
- <date>: <one line>
```
