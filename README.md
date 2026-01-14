# Agent Skills

This repository contains portable Agent Skills (AgentSkills open standard).

## Skills

### `perform-code-review`

Perform adversarial code reviews using the UACRP protocol and report template, writing coordination artifacts under `.local/reports/code_reviews/{YYYY-MM-DD}/` and using a bundled `mpcr` tool for deterministic reviewer/session operations (ID generation, locking, session JSON updates, report writing).

Path: `skills/perform-code-review/`

### `apply-code-review`

Apply code review feedback by consuming completed review reports and updating coordination state (`initiator_status`, applicator notes) in `.local/reports/code_reviews/{YYYY-MM-DD}/_session.json`, using a bundled `mpcr` tool for deterministic waiting, session inspection, status updates, and notes.

Path: `skills/apply-code-review/`

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
- Prebuild `mpcr` in both `skills/*/scripts/mpcr-src` workspaces (`cargo build --locked --release`)

Environment flags:
- `AGENT_SKILLS_SKIP_RUST=1` — skip Rust installation in `scripts/setup.sh`
- `AGENT_SKILLS_SKIP_MPCR_BUILD=1` — skip the `mpcr` prebuild step in either script
