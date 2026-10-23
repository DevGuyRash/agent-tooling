---
name: app-verification
description: Prove that something works for its users by driving the real app the way they do (web, desktop, CLI or TUI, service, mobile, library, or rendered docs) and keeping evidence a reviewer can check, in any repository. Use when asked to verify, demo, or prove that a feature or change works for its users, beyond what tests show, or before reporting user-facing work as done.
---

# App Verification

Prove a change by using the real app the way its user does, and keep evidence a reviewer can check without rerunning it.

## 1. Use the repo's own verification first

Look for a repo-local verification skill: a `verify-*` directory under `.claude/skills/`, `.agents/skills/`, `.codex/skills/`, or `.cursor/skills/`, often with a `features/` map. When one exists, follow it; where it differs from this skill, it wins. When it fails because the app moved on, fixing the skill is part of the work (pstack's `maintain-verification-skill` covers this); say what you changed.

## 2. Otherwise, learn the app from the repo

Answer these from the code, docs, and scripts, and ask the user only what you cannot observe:

- **Surface:** what the user touches: a web UI, desktop or Electron app, CLI or TUI, service API, mobile app, library API, or rendered docs. Pick the one the change reaches; a change can reach several.
- **Run:** the repo's documented dev command (package scripts, justfile, Makefile, README), with its ports, env vars, seed data, and auth.
- **Drive:** the repo's existing harness first (Playwright or Cypress specs, expect scripts, a debug port). Otherwise browser automation for web and Electron, a tmux or PTY session for CLI and TUI, HTTP requests for services, the platform's device tools for mobile, a scratch consumer of the public API for a library, and the reader's own path (rendered pages, followed links) for docs.
- **Observe:** screenshots, terminal transcripts, response bodies, logs, exit codes, and stored state.
- **Isolate:** a port, data directory, and profile of your own. When the app cannot run beside an instance the user already has open, leave theirs alone and say so.

When the app does not build or start, that is the first finding: fix it when it is inside the work, otherwise report the exact failure.

## 3. Run the proof

1. **Launch** from a clean state (empty data directory, migrations, seed data) and wait until the app is usable, not merely listening.
2. **Doctor:** one read-only check that the instance is yours, the right build, and usable.
3. **Drive** the changed behavior along the path a user takes, by stable handles (labels, data attributes, prompt strings, routes) rather than coordinates or tab order. Cover every entry point the change touches.
4. **Capture** the action and the state it produced, including side effects: files written, rows stored, messages sent. Trust a dry-run or test mode only after observing what it actually skips.
5. **Clean up** what you started, by its PID or handle, never by process name. The evidence stays.

The proof uses the real user path, not internal setters or test-only endpoints, and mocks only where a production boundary already isolates the external system. When the data lacks a precondition the journey needs, the journey fails and you report why; the journey stays as the user would walk it.

Keep evidence outside the repo, in `${XDG_STATE_HOME:-$HOME/.local/state}/app-verification/<repo>/<UTC timestamp>/`, and report that path, what you drove, and what each artifact shows.

## 4. Leave the repo easier to verify next time

When the repo has no verification skill and will be verified again, offer once to generate one with pstack's `create-verification-skill`, which writes a repo-local skill and feature map proven against the app. Follow the repo's rules about what may be added to it.
