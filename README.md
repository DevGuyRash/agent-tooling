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
- `just verify-packaging` — verify host refresh plus the committed dist completeness contract
- `just verify-skill-launchers` — smoke-test skill-local launchers against the staged binaries
- `just hooks-install` — point this clone at the committed repo-owned `githooks/` directory for local pre-push checks
- `just harness-doctor` — inspect the current repo shape and local tool availability from the installed harness

`just hooks-install` is local convenience, not the authoritative policy surface. CI and PR gating remain the real enforcement path.

### Contributor hook setup

Repo-owned hooks are committed under `githooks/`, but Git does not execute them automatically from a tracked directory.
Each clone that wants the local pre-push guard must opt into that path once:

- `just hooks-install`
- or `git config --local core.hooksPath githooks`

That updates the clone-local `core.hooksPath` setting so Git runs the committed `githooks/pre-push` script for this repository.

## Packaged binary policy

Normal CI stays lean and Linux-first.
This repository currently pre-packages and commits Linux `dist/` payloads only.
Windows and macOS are no longer supported packaging targets in this repo.

That means:

- `just ci` verifies the committed Linux packaged artifacts
- Linux packaging prefers a fixed `rust:<toolchain>` container when Docker is available, so local `just dist-host` / `just ci` and hosted CI build against the same linker and userspace
- Linux consumers can use the committed skill-local `dist/linux-x86_64/` payloads directly
- Non-Linux hosts are outside the supported packaged-binary contract for this repo

This keeps the repo portable at the skill-directory level for Linux while avoiding heavy cross-OS packaging in routine CI.

## Friction summary output

The friction summary wrappers support multiple output modes:

- `--output-format auto|table|markdown|list`
- `FRICTION_SUMMARY_FORMAT=table|markdown|list`

Use `markdown` or `list` when Unicode box drawing is undesirable, terminal-width detection is unreliable, or the output needs to paste cleanly into plain-text and Markdown surfaces.

## Rust shim pattern

- `skills/code-review/scripts/mpcr`, `skills/docker-architect/scripts/docker-architect-compose`, `skills/docker-architect/scripts/docker-architect-image`, and `skills/friction-diagnostics/scripts/render-table.sh` are skill-local launchers that execute packaged binaries from the same skill directory.
- `scripts/rust-shim-template.sh` is the copy template for future packaged-binary launchers.
- Build and staging are centralized at the repo root through `just` and `scripts/package_skills.py`.
- `packaging/skills.toml` is the single registry for packaged skill binaries, their launcher paths, and which platforms are required in git versus built in CI.
- Portability contract: a skill should not require runtime paths outside its own folder.
- The committed Linux `dist/` payloads are verified in normal CI.
- Packaged launchers in this repo support Linux hosts only.

To add or update a packaged binary, append or edit one `[skills.<id>]` entry in `packaging/skills.toml` and keep these fields aligned:

- `package` — Cargo package name to build
- `binary` — emitted executable name
- `skill_dir` — encapsulated skill directory that owns `dist/<platform-id>/`
- `launcher` — skill-local wrapper script that executes the packaged binary
- `smoke_args` — lightweight launcher verification arguments
- `required_platforms` — committed payloads that must already exist in git
- `ci_platforms` — platforms that automated packaging surfaces should stage for this repo

`scripts/package_skills.py`, `just ci`, and any future packaging workflow all consume that same manifest, so new binaries only need one registry entry rather than parallel updates in multiple places.

Environment flags:
- `AGENT_SKILLS_SKIP_RUST=1` — skip Rust installation in `scripts/setup.sh`
- `AGENT_SKILLS_SKIP_MPCR_BUILD=1` — skip the `mpcr` prebuild step in either script
- `AGENT_SKILLS_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD=1` — skip the `docker-architect-compose` prebuild step in either script
- `AGENT_SKILLS_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD=1` — skip the `docker-architect-image` prebuild step in either script
