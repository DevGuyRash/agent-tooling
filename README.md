# Agent Tooling

This repository contains portable agent tooling: dual-host plugin packages,
host-agnostic skill payloads, Rust-backed launchers, and repo harness scripts.

## Repository layout

Top-level `plugins/` contains plugin packages that may bundle skills, hooks,
MCP servers, apps, and host manifests.
Top-level `skills/` is kept with `.gitkeep` for future standalone,
host-agnostic skill packages that are not distributed as plugins.

WHEN adding a plugin package to this repository THEN you SHALL place it under
`plugins/<plugin-name>/`.
WHEN adding reusable skill content that is not a plugin package THEN you SHALL
place it under `skills/<skill-name>/`.
WHEN a plugin bundles skill instructions THEN you SHALL keep those bundled
skills inside the plugin package's own `skills/` directory.

Marketplace manifests:

- Codex: `.agents/plugins/marketplace.json`
- Claude: `.claude-plugin/marketplace.json`

Current local plugins:

- `plugins/code-review/`
- `plugins/docker-architect/`
- `plugins/espanso-dynamic-forms/`
- `plugins/excel-foundry/`
- `plugins/friction-diagnostics/`
- `plugins/gitops-workflow/`
- `plugins/goal-foundry/` exposes `goal-foundry` for both Codex and Claude and
  bundles the agnostic `$authoring-goals` skill payload.
- `plugins/playwright-testing/`
- `plugins/project-harness/`
- `plugins/rust-development/`
- `plugins/skill-auditor/`

## Plugin Packages

### `code-review`

Unified code review skill with two workflows:

- Reviewer: perform adversarial code reviews using UACRP and produce a structured review report
- Applicator: apply review feedback from completed reports and track dispositions/progress

Both workflows coordinate artifacts under `.local/reports/code_reviews/{YYYY-MM-DD}/` and use a bundled `mpcr` tool for deterministic reviewer/session operations (ID generation, locking, session JSON updates, report writing).

Path: `plugins/code-review/skills/code-review/`

**Migration note:** `perform-code-review` and `apply-code-review` were consolidated into `code-review`. Update any tooling or docs that reference `skills/perform-code-review/` or `skills/apply-code-review/` to use `plugins/code-review/skills/code-review/`.

### `docker-architect`

Deterministic Docker architecture skill spanning both Compose/Swarm deployment design and image supply-chain planning with strict output ordering and traceability IDs (`AC-*`, `IMG-*`, `RSK-*`, `O-*`).

- Compose/Swarm workflow via `plugins/docker-architect/skills/docker-architect/scripts/docker-architect-compose` (packaged-binary launcher)
- Image/build workflow via `plugins/docker-architect/skills/docker-architect/scripts/docker-architect-image` (packaged-binary launcher)
- API-first image metadata refresh with optional scraping fallback
- Cached deterministic render/check workflow for reproducible outputs

Path: `plugins/docker-architect/skills/docker-architect/`

## Plugin portability converter

`scripts/plugin_port.py` converts Codex and Claude Code plugin packages and
marketplaces while preserving source trees and writing a conversion report to
`.plugin-portability/report.json`.

Common commands:

- `python3 scripts/plugin_port.py inspect <path> --format json|md [--from codex|claude]`
- `python3 scripts/plugin_port.py convert <plugin-dir> --to codex|claude --out <output-dir> --mode strict|best-effort [--summary full|json|md]`
- `python3 scripts/plugin_port.py convert-marketplace <marketplace-root-or-json> --to codex|claude --out <output-dir> [--summary full|json|md]`
- `python3 scripts/plugin_port.py validate <plugin-dir> --host codex|claude [--require-external-validator] [--summary full|json|md]`
- `python3 scripts/plugin_port.py roundtrip <plugin-dir> --to codex|claude --tmp <work-dir> [--summary full|json|md]`

Compatibility contract:

- Supported active surfaces: plugin detection, plugin/marketplace inspection,
  Codex skills, Claude skills, Claude commands converted to Codex skills, basic
  manifests, local marketplaces, MCP path normalization, and hook placeholder
  normalization.
- Preserved-only surfaces: Codex apps and plugin-root `CLAUDE.md` files when
  targeting Claude; Claude LSP/output styles/themes/monitors/bin/settings when
  targeting Codex. Root `CLAUDE.md` files are moved to
  `.plugin-portability/preserved/CLAUDE.md` in Claude output because Claude
  plugin validation rejects plugin-root context files.
- Strict rejection surfaces: unsupported hook events, async command hooks,
  handler-level hook filters, non-command hook handlers, invalid JSON/YAML,
  non-local marketplace entries, and marketplace paths that escape the
  marketplace root.
- Best-effort behavior: the source tree is still copied, but semantic loss is
  recorded in `unsupported`, `preserved_only`, and `executable_surfaces`.
  Invalid skill, command, or agent frontmatter is repaired with generated target
  metadata only in best-effort conversion; validation still rejects malformed
  source frontmatter.

Report fields include `schema_version`, `status`, `support_level`,
`validation_summary`, `executable_surfaces`, `warnings`, `unsupported`,
`preserved_only`, `mappings`, and `files_copied`.

Exit codes:

- `0`: success
- `2`: user input or unsupported conversion error
- `3`: validation failure
- `4`: required external validator unavailable

WHEN semantic loss would be unacceptable THEN you SHALL use `--mode strict`.
WHEN publishing converted output THEN you SHALL inspect
`.plugin-portability/report.json` for warnings, unsupported items, preserved-only
items, executable/runtime surfaces, validation summaries, and file mappings.
WHEN external validator parity is required THEN you SHALL run `validate` with
`--require-external-validator`.

Local tests:

- `just test-plugin-port` runs deterministic unit tests.
- `PLUGIN_PORT_LIVE=1 PLUGIN_PORT_CLAUDE=1 just test-plugin-port-live` runs
  Claude CLI checks when `claude` is installed.
- `PLUGIN_PORT_LIVE=1 PLUGIN_PORT_CODEX=1 just test-plugin-port-live` runs Codex
  temp-marketplace checks when `codex` is installed.
- Live tests use temporary directories and a temporary `CODEX_HOME`; they do not
  install into the user's normal plugin state.

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
- Stage host-platform packaged binaries into each plugin-local skill's
  `dist/<platform-id>/` directory

## Repo harness

The repo-local command surface lives in `justfile`.

Common commands:
- `just bootstrap` — install packaging prerequisites used by the repo scripts
- `just verify` — run the fast local verification surface (`fmt-check`, `lint`, `test`)
- `just ci` — run the full repo verification surface, including staged packaging checks
- `just dist-host` — build and stage host-platform packaged binaries into plugin-local skill `dist/` trees
- `just verify-packaging` — verify host refresh plus the committed dist completeness contract
- `just verify-skill-launchers` — smoke-test plugin-local skill launchers against the staged binaries
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
- Linux consumers can use the committed plugin-local skill `dist/linux-x86_64/` payloads directly
- Non-Linux hosts are outside the supported packaged-binary contract for this repo

This keeps the repo portable at the skill-directory level for Linux while avoiding heavy cross-OS packaging in routine CI.

## Friction summary output

The friction summary wrappers support multiple output modes:

- `--output-format auto|table|markdown|list`
- `FRICTION_SUMMARY_FORMAT=table|markdown|list`

Use `markdown` or `list` when Unicode box drawing is undesirable, terminal-width detection is unreliable, or the output needs to paste cleanly into plain-text and Markdown surfaces.

## Rust shim pattern

- `plugins/code-review/skills/code-review/scripts/mpcr`, `plugins/docker-architect/skills/docker-architect/scripts/docker-architect-compose`, `plugins/docker-architect/skills/docker-architect/scripts/docker-architect-image`, and `plugins/friction-diagnostics/skills/friction-diagnostics/scripts/render-table.sh` are plugin-local skill launchers that execute packaged binaries from the same skill directory.
- `scripts/rust-shim-template.sh` is the copy template for future packaged-binary launchers.
- Build and staging are centralized at the repo root through `just` and `scripts/package_skills.py`.
- `packaging/skills.toml` is the single registry for packaged plugin-local skill binaries, their launcher paths, and which platforms are required in git versus built in CI.
- Portability contract: a plugin-local skill should not require runtime paths outside its own folder.
- The committed Linux `dist/` payloads are verified in CI only when packaging-relevant files changed.
- Packaged launchers in this repo support Linux hosts only.

To add or update a packaged binary, append or edit one `[skills.<id>]` entry in `packaging/skills.toml` and keep these fields aligned:

- `package` — Cargo package name to build
- `binary` — emitted executable name
- `skill_dir` — encapsulated plugin-local skill directory that owns `dist/<platform-id>/`
- `launcher` — plugin-local skill wrapper script that executes the packaged binary
- `smoke_args` — lightweight launcher verification arguments
- `required_platforms` — committed payloads that must already exist in git
- `ci_platforms` — platforms that automated packaging surfaces should stage for this repo

`scripts/package_skills.py`, `just ci`, and any future packaging workflow all consume that same manifest, so new binaries only need one registry entry rather than parallel updates in multiple places.

Environment flags:

- `AGENT_TOOLING_SKIP_RUST=1` — skip Rust installation in `scripts/setup.sh`
- `AGENT_TOOLING_SKIP_MPCR_BUILD=1` — skip the `mpcr` prebuild step in setup/maintenance
- `AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD=1` — skip the `docker-architect-compose` prebuild step in setup/maintenance
- `AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD=1` — skip the `docker-architect-image` prebuild step in setup/maintenance
- `AGENT_TOOLING_DIST_BUILD_MODE=auto|container|host` — choose host or containerized dist builds
- `AGENT_TOOLING_RUST_IMAGE=<image>` — override the Rust container image used for Linux dist builds

Deprecated `AGENT_SKILLS_*` names remain accepted as aliases.
