# Agent Tooling

This repository contains portable agent tooling: host-aware plugin packages, host-agnostic skill payloads, Rust-backed launchers, and repo harness scripts.

After cloning for contributor work, run `just bootstrap` to enable the Git hooks and check artifact readiness. See [contributor setup](#contributor-setup) for prerequisites and task selection.

## Repository layout

Top-level `plugins/` contains plugin packages that may bundle skills, hooks, MCP servers, apps, and host manifests. Top-level `skills/` is kept with `.gitkeep` for future standalone, host-agnostic skill packages that are not distributed as plugins.

WHEN adding a plugin package to this repository THEN you SHALL place it under `plugins/<plugin-name>/`. WHEN adding reusable skill content that is not a plugin package THEN you SHALL place it under `skills/<skill-name>/`. WHEN a plugin bundles skill instructions THEN you SHALL keep those bundled skills inside the plugin package's own `skills/` directory.

Marketplace manifests:

- Codex: `.agents/plugins/marketplace.json`
- Claude: `.claude-plugin/marketplace.json`

The catalogs are independent. Most plugins support both hosts; a plugin that depends on a host-native runtime or instruction surface is published only for the capable host.

Current usage and resource requirements live with each plugin. The [documentation index](docs/README.md) separates repository-wide architecture decisions from plugin-specific documentation. ADRs record current architecture choices and their rationale; `AGENTS.md`, target contracts, host schemas, and maker requirements remain authoritative.

Keep raw trial captures, release verification records, transcripts, scratch investigations, and installation inventories under the ignored `.local/context/` directory. Maintain durable architecture rationale and useful user documentation in the repository; age or document type alone does not make a record disposable.

Current local plugins:

- `plugins/chatgpt-browser/` provides portable ChatGPT conversation, context, attachment, model-selection, and thread-hygiene guidance when an authorized interactive-browser controller is available.
- `plugins/docker-architect/`
- `plugins/espanso-dynamic-forms/`
- `plugins/excel-foundry/`
- `plugins/visualization/`
- `plugins/goalspec/` exposes `goalspec` for both Codex and Claude and bundles the agnostic `$authoring-goals` skill payload.
- `plugins/playwright-testing/`
- `plugins/project-harness/`
- [Agentic Design & Evaluation](plugins/agentic-design-and-evaluation/README.md) provides Prompt and Context Design, Skill Auditor, Split Testing, Self-Healing, and Foundational Knowledge. Its shared references are the maintained masters; Split Testing owns comparative methodology. Entries support the same assignment without automatic workflow chaining. Self-Healing uses the assignment’s existing tools and retained evidence.

Agentic Design & Evaluation is distributed as a complete plugin. Its task skills depend on the public shared resources listed in its package guide; a copied task-skill directory is not a supported standalone installation. This package boundary is distinct from a launcher or standalone skill that promises to carry all of its dependencies inside one skill directory.
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

- `just bootstrap` — enable contributor hooks, verify artifacts and report missing build tools
- `just verify` — run the fast local verification surface (`fmt-check`, `lint`, `test`)
- `just ci` — fetch Rust dependencies and run repository, artifact and launcher checks without changing hook configuration or tracked distribution payloads
- `scripts/install-all` / `just install-all` — reconcile selected catalog entries by version and source digest without touching already-current plugins
- `just dist-host` — build and stage host-platform packaged binaries into plugin-local skill `dist/` trees
- `just verify-packaging` — check task receipts and delivered outputs without mutation
- `just verify-skill-launchers` — smoke-test plugin-local skill launchers against the staged binaries
- `just audit-plugins [name ...]` — report what the skill-auditor's scripts observe about every plugin, or the named ones (`--errors-only` omits the observations)
- `just hooks-install` — activate staged-input generation and outgoing-revision checks in this clone
- `just harness-doctor` — inspect the current repo shape and local tool availability from the installed harness

`just artifacts-sync` synchronizes changed task outputs; `just artifacts-check` verifies accepted content without running producers. `just mermaid-refresh` explicitly captures upstream documentation and regenerates the two Mermaid references. [Artifact synchronization](docs/artifacts.md) explains task definitions, receipts, hooks, recovery and prerequisites.

`just audit-plugins` prints what the auditor's scripts can observe and fails only on what is broken for every target. Facts whose significance depends on the target — lengths, naming, house idiom — are printed with the reference that owns the rule, and never fail; a script cannot see a target's age or profile, so judging those is the reader's. Run `scripts/audit-plugins.sh --help` for the current contract — that text is canonical, so this paragraph does not restate it. CI audits only the plugins a change touches, so one plugin's backlog blocks nobody else's work.

### Install all plugins

Run this from a clone when you want this repo's plugin catalogs available in the supported CLIs. This is a developer bootstrap helper for `agent-tooling`; a separate configuration repository should own durable workstation selection and pruning.

```bash
scripts/install-all
```

By default it uses the GitHub marketplace source `DevGuyRash/agent-tooling` with sparse checkout paths for each host:

- Codex: `.agents/plugins` plus `plugins`
- Claude Code: `.claude-plugin` plus `plugins`

The script resolves the exact local or remote source, reads each host marketplace independently, and identifies every selected plugin by version plus a canonical source-tree digest. It adds missing marketplace/plugin state and updates only a proven identity difference. Before selected installs or updates, it refreshes an existing Git marketplace snapshot so newly published names and artifacts are available. For a mutating run that includes Claude, it snapshots the observed version-2 native registry before any host mutation and restores only missing non-selected registrations, including other scopes and other projects of selected plugins. Guard activation follows the whole selected transaction, even when Claude itself needs no update. Only identities actually being installed or updated are exempt, and receipts and verification retain the requested scope/project identity. Conflicting changed records cause failure instead of being overwritten; an unreadable post-operation registry is restored to its pre-operation state and reported as a failure. This protects a single installation transaction and does not reconcile workstation desired state. A second run against unchanged source performs discovery and verification but invokes no marketplace or plugin mutations. Its atomic receipt is `${XDG_STATE_HOME:-~/.local/state}/agent-tooling/install-all.json`.

Claude's native update compares versions. For changed content at the same version, an explicit force, or marketplace replacement, the installer removes only the selected scope's declaration with `--keep-data` and installs the resolved package again. Scoped activation choices are preserved, including disabled plugins and inherited settings. Pending choices remain in `install-all-activation.json` beside the receipt until the installed files match the candidate digest. If the reinstall is interrupted or fails, rerun the same `install-all` command to finish; persistent plugin data and the previous success receipt remain available.

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

### `agentic-design-and-evaluation` migration

Agentic Design & Evaluation replaces the `skill-auditor` and `split-testing` plugin identities while retaining their skill invocation slugs inside the new package. After the release reaches `DevGuyRash/agent-tooling@main`, run `scripts/install-all --include agentic-design-and-evaluation` with the normal canonical source. Verify the new package on both intended hosts before retiring either old installation.

For old installations in the user scope, the selected retirement commands are:

```sh
codex plugin remove skill-auditor@agent-tooling
codex plugin remove split-testing@agent-tooling
claude plugin uninstall --scope user --keep-data skill-auditor@agent-tooling
claude plugin uninstall --scope user --keep-data split-testing@agent-tooling
```

For project/local installation, run the installer from the intended native project directory. The observed Claude CLI records its process working directory as `projectPath`, which can differ from the containing Git root or the local settings-file location. Inspect the actual installed scopes first; do not remove a separate project or local declaration by assumption. These commands select the two old user-scope identities and request retention of old Claude plugin data. Verify unrelated registrations and settings before and after retirement; the installation safeguard is not a general rollback or isolation guarantee for arbitrary later CLI commands. Removing an old marketplace entry alone does not uninstall its cached copy. A running session can retain old instructions; a fresh session is needed for the new catalog and package.

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

### Contributor setup

After cloning, run `just bootstrap` from the repository root. Git and Python 3.11+ are required. Without `just`, use `python3 scripts/artifacts.py bootstrap`. This enables the maintained pre-commit and pre-push hooks, checks artifact receipts and outputs, and reports missing build tools by task. Rerunning it is safe. A current checkout needs no compiler to complete this setup; no producer, upstream refresh or dependency installer runs.

Pre-commit generates automatic tasks from staged inputs and stages their outputs and receipts, preserving unrelated work. Pre-push verifies outgoing revisions. Build tools become necessary when their tasks need regeneration. Use `just bootstrap --task visual_library --require-tools` to require executable availability for a selected contribution area; task producers enforce pinned versions when building. `just rust-fetch` explicitly fetches the Rust workspace’s locked dependencies.

Existing custom hook configuration is preserved. `just bootstrap --replace-hooks` explicitly selects the repository hooks while retaining the old hook files. `just hooks-install` uses the same installer when only hook activation is wanted. Git does not activate repository hook files merely by cloning. Publication, plugin installation and upstream refresh remain explicit operations.

## Artifact delivery

[packaging/artifacts.toml](packaging/artifacts.toml) declares every maintained artifact task. Each declaration names source inputs, a command when needed, outputs, destinations, dependencies and runtime requirements. Rust builds, generated browser assets, Mermaid references and resource copies use the same synchronization engine. Installed packages receive their own required resources.

- `just artifacts-sync` prepares changed automatic tasks and synchronizes verified outputs.
- `just artifacts-sync --task <id>` selects a task and its declared dependencies.
- `just artifacts-check` verifies content fingerprints and output identities without rebuilding.
- `just mermaid-refresh` captures current official Mermaid documentation, then generates references for the bundled renderer and broader documentation.
- `just visual-previews` assembles standalone local report examples.

See [Artifact synchronization](docs/artifacts.md) for the maintained contract and examples. Task receipts travel with committed outputs; optional logs and preview receipts stay local. A fresh checkout can verify committed delivery without fetching upstream or rebuilding Rust.

## Rust launchers

Docker Architect’s Compose and image launchers execute the matching binary under their skill’s `dist/<platform>/` directory. `scripts/rust-shim-template.sh` provides the reusable launcher form. The task’s `parameters.rust` selects the pinned release recipe; `scripts/build_rust_artifacts.py` prepares two independent builds and compares their bytes before delivery. The current Docker Architect deliveries target Linux x86-64.

`scripts/package_skills.py` retains the existing packaging command names as adapters over the task engine. `stage-host` and `dist-refresh` synchronize selected Rust tasks; verification commands check their receipts without rebuilding. `sync-artifacts` imports prepared outputs only with matching task receipts and source identities. `vendor` operates on direct-copy tasks. The manifest, receipt format and publication logic have one maintained owner.

Setup flags remain documented by `scripts/setup.sh` and `scripts/maintenance.sh`. Plugin installation uses the explicit installer described above.
