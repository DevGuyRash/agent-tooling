# Agent Skills

This repository contains portable Agent Skills (AgentSkills open standard).

## Skills

### `code-review`

Unified code review skill with two workflows:

- Reviewer: perform adversarial code reviews using UACRP and produce a structured review report
- Applicator: apply review feedback from completed reports and track dispositions/progress

Both workflows coordinate artifacts under `.local/reports/code_reviews/{YYYY-MM-DD}/` and use a bundled `mpcr` tool for deterministic reviewer/session operations (ID generation, locking, session JSON updates, report writing).

Path: `skills/code-review/`

**Migration note:** `perform-code-review` and `apply-code-review` were consolidated into `code-review`. Update any tooling or docs that reference `skills/perform-code-review/` or `skills/apply-code-review/` to use `skills/code-review/`.

## Container bootstrap scripts

These scripts are repo-wide (not skill-specific) and are intended for:
- AI agent runners that create a new container and then clone this repo
- CI/CD systems that reuse cached containers/workspaces

They are optional: each skill ships an `mpcr` shim that auto-builds on first run, but the scripts below make environments more deterministic by ensuring Rust is available and by prebuilding binaries up front.

- Fresh container (after clone): `scripts/setup.sh`
- Cached container (after checkout): `scripts/maintenance.sh`

Both scripts:
- Ensure `.local/reports/code_reviews/` exists (gitignored)
- Best-effort add the repo root to git `safe.directory`
- Prebuild `mpcr` in `skills/code-review/scripts/mpcr-src` (`cargo build --locked --release`)

Environment flags:
- `AGENT_SKILLS_SKIP_RUST=1` — skip Rust installation in `scripts/setup.sh`
- `AGENT_SKILLS_SKIP_MPCR_BUILD=1` — skip the `mpcr` prebuild step in either script
