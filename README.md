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

### `docker-architect`

Deterministic Docker architecture skill spanning both Compose/Swarm deployment design and image supply-chain planning with strict output ordering and traceability IDs (`AC-*`, `IMG-*`, `RSK-*`, `O-*`).

- Compose/Swarm workflow via `skills/docker-architect/scripts/docker-architect-compose` (packaged-binary launcher)
- Image/build workflow via `skills/docker-architect/scripts/docker-architect-image` (packaged-binary launcher)
- API-first image metadata refresh with optional scraping fallback
- Cached deterministic render/check workflow for reproducible outputs

Path: `skills/docker-architect/`

## Container bootstrap scripts

These scripts are repo-wide (not skill-specific) and are intended for:
- AI agent runners that create a new container and then clone this repo
- CI/CD systems that reuse cached containers/workspaces

They are optional, but recommended for deterministic environments because they ensure Rust is available and prebuild binaries up front.
Single-skill installs should invoke each skill's local launcher under `<skills-file-root>/scripts/`.

- Fresh container (after clone): `scripts/setup.sh`
- Cached container (after checkout): `scripts/maintenance.sh`

Both scripts:
- Ensure `.local/reports/code_reviews/` exists (gitignored)
- Best-effort add the repo root to git `safe.directory`
- Bootstrap the root Rust workspace
- Stage host-platform packaged binaries into each skill's `dist/<platform-id>/` directory

## Repo harness

The repo-local command surface lives in `justfile`.

Common commands:
- `just bootstrap` — install packaging prerequisites used by the repo scripts
- `just verify` — run the fast local verification surface (`fmt-check`, `lint`, `test`)
- `just ci` — run the full repo verification surface, including staged packaging checks
- `just dist-host` — build and stage host-platform packaged binaries into the skill `dist/` trees
- `just verify-skill-launchers` — smoke-test skill-local launchers against the staged binaries
- `just harness-doctor` — inspect the current repo shape and local tool availability from the installed harness

## Rust shim pattern

- `skills/code-review/scripts/mpcr`, `skills/docker-architect/scripts/docker-architect-compose`, `skills/docker-architect/scripts/docker-architect-image`, and `skills/friction-diagnostics/scripts/render-table.sh` are skill-local launchers that execute packaged binaries from the same skill directory.
- `scripts/rust-shim-template.sh` is the copy template for future packaged-binary launchers.
- Build and staging are centralized at the repo root through `just` and `scripts/package_skills.py`.
- Portability contract: a skill should not require runtime paths outside its own folder.

Environment flags:
- `AGENT_SKILLS_SKIP_RUST=1` — skip Rust installation in `scripts/setup.sh`
- `AGENT_SKILLS_SKIP_MPCR_BUILD=1` — skip the `mpcr` prebuild step in either script
- `AGENT_SKILLS_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD=1` — skip the `docker-architect-compose` prebuild step in either script
- `AGENT_SKILLS_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD=1` — skip the `docker-architect-image` prebuild step in either script
