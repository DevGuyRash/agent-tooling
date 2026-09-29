# Agent instructions

This file is where we keep the rules for AI agents working in this repository. People add to it over time, so each entry is dated; when two entries disagree, the later date is the current decision, wherever the entry sits in the file.

## General

- (2026-06) The Makefile was removed. Run the tests with `just test` before you push, not `make test`.
- (2025-09) Use conventional commits (`feat:`, `fix:`, `chore:` and so on) for every commit message.
- (2026-07) CHANGELOG.md is now generated from commit messages at release time. Don't edit CHANGELOG.md by hand anymore.
- (2025-10) Never commit secrets, API keys, or `.env` files.
- (2025-09) Don't write long pull requests. Keep pull requests small.
- (2025-11) Do not add a new third-party dependency without asking the maintainers first in the issue.

## Code style

- (2026-04) Update: we switched the formatter. Use 4 spaces for Python indentation, never tabs.
- (2025-10) Don't leave public functions without type hints. All public functions need type hints.
- (2026-02) Avoid giant pull requests; reviewers can't review more than about 400 changed lines well, so stay under that.
- (2026-04) Run `just lint` before pushing; it runs ruff and mypy.

## Git

- (2026-05) Name branches `<ticket>-<short-slug>`, for example `ACME-412-retry-webhooks`.
- (2026-03) Never push directly to `main`; every change reaches `main` through a reviewed pull request.
- (2026-01) Don't forget: commit messages must follow conventional commits.
- (2026-05) As mentioned above, don't put secrets in commits. This includes tokens in test fixtures.

## Misc

- (2025-11) Indent Python with tabs.
- (2026-01) Name branches `feature/<ticket>`.
- (2025-10) Run the tests with `make test` before you push.
- (2025-12) Update CHANGELOG.md in every pull request with a line describing your change.
- (2026-06) NOTE: please don't add dependencies on your own; ask first (see above).
- (2026-07) Reminder: conventional commits, always.
- (2026-08) Don't open huge PRs. Small PRs only.
