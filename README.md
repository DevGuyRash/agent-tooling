# Agent Tooling

This repository contains portable agent tooling: host-aware plugin packages, host-agnostic skill payloads, Rust-backed launchers, and repo harness scripts.

## Repository layout

Top-level `plugins/` contains plugin packages that may bundle skills, hooks, MCP servers, apps, and host manifests. Top-level `skills/` is kept with `.gitkeep` for future standalone, host-agnostic skill packages that are not distributed as plugins.

WHEN adding a plugin package to this repository THEN you SHALL place it under `plugins/<plugin-name>/`. WHEN adding reusable skill content that is not a plugin package THEN you SHALL place it under `skills/<skill-name>/`. WHEN a plugin bundles skill instructions THEN you SHALL keep those bundled skills inside the plugin package's own `skills/` directory.

Marketplace manifests:

- Codex: `.agents/plugins/marketplace.json`
- Claude: `.claude-plugin/marketplace.json`

The catalogs are independent. Most plugins support both hosts; a plugin that depends on a host-native runtime or instruction surface is published only for the capable host.

Reusable instruction and evaluation decisions, their outcome evidence, and reopening conditions are indexed in [`docs/adr/`](docs/adr/README.md). The ADRs record rationale; `AGENTS.md`, target contracts, host schemas, and maker requirements remain authoritative.

Current local plugins:

- `plugins/chatgpt-browser/` provides portable ChatGPT conversation, context, attachment, model-selection, and thread-hygiene guidance when an authorized interactive-browser controller is available.
- `plugins/docker-architect/`
- `plugins/espanso-dynamic-forms/`
- `plugins/excel-foundry/`
- `plugins/friction-diagnostics/`
- `plugins/goalspec/` exposes `goalspec` for both Codex and Claude and bundles the agnostic `$authoring-goals` skill payload.
- `plugins/playwright-testing/`
- `plugins/project-harness/`
- `plugins/skill-auditor/` owns audit disposition and delegates newly needed comparative evidence to Split Testing in ordinary context without a hard plugin dependency.
- `plugins/split-testing/` owns generic comparative-evidence method without owning domain truth, maker values, audit disposition, a caller format, or an execution harness.
- `plugins/software-development/` replaces `rust-development` and `gitops-workflow` with a shared development catalog for both Codex and Claude Code.

## Plugin Packages

### `docker-architect`

Deterministic Docker architecture skill spanning both Compose/Swarm deployment design and image supply-chain planning with strict output ordering and traceability IDs (`AC-*`, `IMG-*`, `RSK-*`, `O-*`).

- Compose/Swarm workflow via `plugins/docker-architect/skills/docker-architect/scripts/docker-architect-compose` (packaged-binary launcher)
- Image/build workflow via `plugins/docker-architect/skills/docker-architect/scripts/docker-architect-image` (packaged-binary launcher)
- API-first image metadata refresh with optional scraping fallback
- Cached deterministic render/check workflow for reproducible outputs

Path: `plugins/docker-architect/skills/docker-architect/`

## Plugin portability converter

`scripts/plugin_port.py` converts Codex and Claude Code plugin packages and marketplaces while preserving source trees and writing a conversion report to `.plugin-portability/report.json`.

Common commands:

- `python3 scripts/plugin_port.py inspect <path> --format json|md [--from codex|claude]`
- `python3 scripts/plugin_port.py convert <plugin-dir> --to codex|claude --out <output-dir> --mode strict|best-effort [--summary full|json|md]`
- `python3 scripts/plugin_port.py convert-marketplace <marketplace-root-or-json> --to codex|claude --out <output-dir> [--summary full|json|md]`
- `python3 scripts/plugin_port.py validate <plugin-dir> --host codex|claude [--require-external-validator] [--summary full|json|md]`
- `python3 scripts/plugin_port.py roundtrip <plugin-dir> --to codex|claude --tmp <work-dir> [--summary full|json|md]`

Compatibility contract:

- Supported active surfaces: plugin detection, plugin/marketplace inspection, Codex skills, Claude skills, Claude commands converted to Codex skills, basic manifests, local marketplaces, MCP path normalization, and hook placeholder normalization.
- Preserved-only surfaces: Codex apps and plugin-root `CLAUDE.md` files when targeting Claude; Claude LSP/output styles/themes/monitors/bin/settings when targeting Codex. Root `CLAUDE.md` files are moved to `.plugin-portability/preserved/CLAUDE.md` in Claude output because Claude plugin validation rejects plugin-root context files.
- Strict rejection surfaces: unsupported hook events, async command hooks, handler-level hook filters, non-command hook handlers, invalid JSON/YAML, non-local marketplace entries, marketplace paths that escape the marketplace root, and MCP runtime paths that escape the plugin root.
- Roundtrips use strict mode by default and internally validate the converted second-hop plugin. Codex external validation resolves its bundled validator below `CODEX_HOME` when that environment variable is set.
- Best-effort behavior: the source tree is still copied, but semantic loss is recorded in `unsupported`, `preserved_only`, and `executable_surfaces`. Invalid skill, command, or agent frontmatter is repaired with generated target metadata only in best-effort conversion; validation still rejects malformed source frontmatter.

Report fields include `schema_version`, `status`, `support_level`, `validation_summary`, `executable_surfaces`, `warnings`, `unsupported`, `preserved_only`, `mappings`, and `files_copied`.

Exit codes:

- `0`: success
- `2`: user input or unsupported conversion error
- `3`: validation failure
- `4`: required external validator unavailable

WHEN semantic loss would be unacceptable THEN you SHALL use `--mode strict`. WHEN publishing converted output THEN you SHALL inspect `.plugin-portability/report.json` for warnings, unsupported items, preserved-only items, executable/runtime surfaces, validation summaries, and file mappings. WHEN external validator parity is required THEN you SHALL run `validate` with `--require-external-validator`.

Local tests:

- `just test-plugin-port` runs deterministic unit tests.
- `PLUGIN_PORT_LIVE=1 PLUGIN_PORT_CLAUDE=1 just test-plugin-port-live` runs Claude CLI checks when `claude` is installed.
- `PLUGIN_PORT_LIVE=1 PLUGIN_PORT_CODEX=1 just test-plugin-port-live` runs Codex temp-marketplace checks when `codex` is installed.
- Live tests use temporary directories and a temporary `CODEX_HOME`; they do not install into the user's normal plugin state.

## Container bootstrap scripts

These scripts are repo-wide (not skill-specific) and are intended for:

- AI agent runners that create a new container and then clone this repo
- CI/CD systems that reuse cached containers/workspaces

They are optional, but recommended for deterministic environments because they ensure Rust is available and prebuild binaries up front. Single-skill installs should invoke each skill's local launcher under `<skills-file-root>/scripts/`.

- Fresh container (after clone): `scripts/setup.sh`
- Cached container (after checkout): `scripts/maintenance.sh`

Both scripts:

- Ensure `.local/reports/code_reviews/` exists (gitignored)
- Best-effort add the repo root to git `safe.directory`
- Bootstrap the root Rust workspace
- Stage host-platform packaged binaries into each plugin-local skill's `dist/<platform-id>/` directory

## Repo harness

The repo-local command surface lives in `justfile`.

Common commands:

- `just bootstrap` — install packaging prerequisites used by the repo scripts
- `just verify` — run the fast local verification surface (`fmt-check`, `lint`, `test`)
- `just ci` — run bootstrap, repository verification, and launcher checks without rewriting tracked distribution payloads
- `scripts/install-all` / `just install-all` — reconcile selected catalog entries by version and source digest without touching already-current plugins
- `just dist-host` — build and stage host-platform packaged binaries into plugin-local skill `dist/` trees
- `just verify-packaging` — verify host refresh plus the committed dist completeness contract
- `just verify-skill-launchers` — smoke-test plugin-local skill launchers against the staged binaries
- `just audit-plugins [name ...]` — report what the skill-auditor's scripts observe about every plugin, or the named ones (`--errors-only` omits the observations)
- `just hooks-install` — point this clone at the committed repo-owned `githooks/` directory for the local pre-push check
- `just harness-doctor` — inspect the current repo shape and local tool availability from the installed harness

`just hooks-install` only opts the current clone into the tracked pre-push guard. `just verify-packaging` checks packaged-artifact completeness without refreshing artifacts, while release payloads change only through the explicit local refresh workflow.

`just audit-plugins` prints what the auditor's scripts can observe and fails only on what is broken for every target. Facts whose significance depends on the target — lengths, naming, house idiom — are printed with the reference that owns the rule, and never fail; a script cannot see a target's age or profile, so judging those is the reader's. Run `scripts/audit-plugins.sh --help` for the current contract — that text is canonical, so this paragraph does not restate it. CI audits only the plugins a change touches, so one plugin's backlog blocks nobody else's work.

### Install all plugins

Run this from a clone when you want this repo's plugin catalogs available in the supported CLIs. This is a developer bootstrap helper for `agent-tooling`; a separate configuration repository should own durable workstation selection and pruning.

```bash
scripts/install-all
```

By default it uses the GitHub marketplace source `DevGuyRash/agent-tooling` with sparse checkout paths for each host:

- Codex: `.agents/plugins` plus `plugins`
- Claude Code: `.claude-plugin` plus `plugins`

The script resolves the exact local or remote source, reads each host marketplace independently, and identifies every selected plugin by version plus a canonical source-tree digest. It adds missing marketplace/plugin state and updates only a proven identity difference. A second run against unchanged source performs discovery and verification but invokes no marketplace or plugin mutations. Its atomic receipt is `${XDG_STATE_HOME:-~/.local/state}/agent-tooling/install-all.json`.

Filter the dynamic plugin list with repeatable CSV/glob flags:

```bash
scripts/install-all --exclude 'software-development'
scripts/install-all --include 'goalspec,project-harness' --exclude 'project-*'
```

Filters are applied independently to enabled host catalogs. A host-specific selection skips the other host without error. A host-only run fails clearly when an include pattern has no match in that host's catalog.

Limit the target host when needed:

```bash
scripts/install-all --codex-only
scripts/install-all --claude-only
```

The `just` recipe forwards the same flags:

```bash
just install-all --exclude 'software-development'
```

Use `scripts/install-all --help` for source, scope, host, filter, force, and dry-run options. A source mismatch fails before mutation unless `--replace-marketplace` is explicit; replacement invalidates the matching receipt identity and rematerializes selected plugins while limiting Claude removal to the selected `--claude-scope`. `--force` explicitly reinstalls every selected plugin and permits a downgrade. The script shares syscfg's agent-plugin lifecycle lock, does not replace or unset `CODEX_HOME`, and prints a restart warning only after replacing a plugin root.

### `software-development` migration

The `software-development` plugin replaces both `rust-development` and `gitops-workflow`. Remove the legacy plugin identities before installing the new catalog, then start a fresh task or restart the host so discovery reloads against the new skill set:

```bash
codex plugin remove rust-development@agent-tooling
codex plugin remove gitops-workflow@agent-tooling
codex plugin add software-development@agent-tooling

claude plugin remove rust-development@agent-tooling
claude plugin remove gitops-workflow@agent-tooling
claude plugin install software-development@agent-tooling
```

### Contributor hook setup

Repo-owned hooks are committed under `githooks/`, but Git does not execute them automatically from a tracked directory. Each clone that wants the local push guard must opt into that path once:

- `just hooks-install`
- or `git config --local core.hooksPath githooks`

That updates the clone-local `core.hooksPath` setting so Git runs the committed `githooks/pre-push` script for this repository.

## Packaged binary policy

Each packaged skill declares its exact committed target matrix in `packaging/skills.toml`. A platform is supported only when that skill's declared matrix and smoke contract cover it. Split Testing is instruction-only and has no packaged executable.

That means:

- `just ci` verifies the repository without rewriting tracked `dist/` trees
- `just dist-host` is the explicit host-platform refresh route for packaged skills
- consumers use only the platform payloads declared for the specific skill

This keeps ordinary verification non-mutating while making every executable capability and platform claim skill-specific.

## Friction summary output

The friction summary wrappers support multiple output modes:

- `--output-format auto|table|markdown|list`
- `FRICTION_SUMMARY_FORMAT=table|markdown|list`

Use `markdown` or `list` when Unicode box drawing is undesirable, terminal-width detection is unreliable, or the output needs to paste cleanly into plain-text and Markdown surfaces.

## Rust shim pattern

- `plugins/docker-architect/skills/docker-architect/scripts/docker-architect-compose`, `plugins/docker-architect/skills/docker-architect/scripts/docker-architect-image`, and `plugins/friction-diagnostics/skills/friction-diagnostics/scripts/render-table.sh` are plugin-local skill launchers that execute packaged binaries from the same skill directory.
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
- `AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD=1` — skip the `docker-architect-compose` prebuild step in setup/maintenance
- `AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD=1` — skip the `docker-architect-image` prebuild step in setup/maintenance
- `AGENT_TOOLING_DIST_BUILD_MODE=auto|container|host` — choose host or containerized dist builds
- `AGENT_TOOLING_RUST_IMAGE=<image>` — override the Rust container image used for Linux dist builds

Deprecated `AGENT_SKILLS_*` names remain accepted as aliases.
