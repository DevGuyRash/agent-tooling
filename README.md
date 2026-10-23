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
- `plugins/espanso-dynamic-forms/`
- `plugins/excel-foundry/`
- [Visualization](plugins/visualization/README.md) helps an agent visualize anything in whatever form serves its audience, exploring genuinely different directions before committing and presenting the information faithfully; it includes a Mermaid format guide.
- [Playwright Testing](plugins/playwright-testing/README.md) provides outcome-oriented test design and execution, Browser Survey, and shared capture, evidence and isolated-session helpers.
- `plugins/project-harness/`
- [Agentic Design & Evaluation](plugins/agentic-design-and-evaluation/README.md) provides Prompt and Context Design, Skill Auditor, Split Testing, Self-Healing, and Foundational Knowledge. Its shared references are the maintained masters; Split Testing owns comparative methodology. Entries support the same assignment without automatic workflow chaining. Self-Healing uses the assignment’s existing tools and retained evidence.

Agentic Design & Evaluation is distributed as a complete plugin. Its task skills depend on the public shared resources listed in its package guide; a copied task-skill directory is not a supported standalone installation. This package boundary is distinct from a launcher or standalone skill that promises to carry all of its dependencies inside one skill directory.
- `plugins/software-development/` replaces `rust-development` and `gitops-workflow` with a shared development catalog for both Codex and Claude Code.

## Archived packages

`diagram`, `docker-architect`, and `goalspec` are retired from active discovery and installation. Their complete payloads are retained under [archived/](archived/README.md), with restoration and existing-installation retirement guidance. Visualization and Mermaid remain active.

## Plugin portability converter

`scripts/plugin_port.py` converts Codex and Claude Code plugin packages and marketplaces while preserving source trees and writing a conversion report to `.plugin-portability/report.json`.

Common commands:

- `python3 scripts/plugin_port.py inspect <path> --format json|md [--from codex|claude]`
- `python3 scripts/plugin_port.py convert <plugin-dir> --to codex|claude --out <output-dir> --mode strict|best-effort [--summary full|json|md]`
- `python3 scripts/plugin_port.py convert-marketplace <marketplace-root-or-json> --to codex|claude --out <output-dir> [--summary full|json|md]`
- `python3 scripts/plugin_port.py validate <plugin-dir> --host codex|claude [--require-external-validator] [--summary full|json|md]`
- `python3 scripts/plugin_port.py roundtrip <plugin-dir> --to codex|claude --tmp <work-dir> [--summary full|json|md]`

Compatibility contract:

- Supported active surfaces: bidirectional native custom-agent definition conversion, plugin detection, plugin/marketplace inspection, Codex skills, Claude skills, Claude commands converted to Codex skills, basic manifests, local marketplaces, MCP path normalization, and hook placeholder normalization.
- Preserved-only surfaces: Codex apps and plugin-root `CLAUDE.md` files when targeting Claude; Claude LSP/output styles/themes/monitors/bin/settings when targeting Codex. Root `CLAUDE.md` files are moved to `.plugin-portability/preserved/CLAUDE.md` in Claude output because Claude plugin validation rejects plugin-root context files.
- Strict rejection surfaces: unsupported hook events, async command hooks, handler-level hook filters, non-command hook handlers, invalid JSON/YAML, non-local marketplace entries, marketplace paths that escape the marketplace root, and MCP runtime paths that escape the plugin root.
- Roundtrips use strict mode by default and internally validate the converted second-hop plugin. Codex external validation resolves its bundled validator below `CODEX_HOME` when that environment variable is set.
- Best-effort behavior: the source tree is still copied, but semantic loss is recorded in `unsupported`, `preserved_only`, and `executable_surfaces`. Invalid skill or command frontmatter may be repaired with generated target metadata in best-effort conversion. Malformed agents and unsupported agent restrictions fail before output mutation in both modes.

### Custom agents

Claude plugin agents are Markdown files with YAML frontmatter. Codex custom agents are TOML files. The converter adapts their name, description, instructions, explicit model selection and compatible effort fields in both directions. Instructions retain their original bytes. The converter does not rewrite prose that assumes host-specific tools or runtime variables. Review those assumptions separately. It preserves the source definitions for roundtrips.

Codex does not load agents from a plugin manifest. Converted definitions live under `.codex/agents/` inside the package until an installer projects them into `$CODEX_HOME/agents/`, or `~/.codex/agents/` when `CODEX_HOME` is unset. Claude loads converted `agents/*.md` through its native plugin installation. A copied definition is not proof that either host invoked it.

Three rules keep conversion independent of each host's growing list of settings:

- **Same host:** a definition projected to its own host keeps every key unchanged, so the host decides what it honors, exactly as for a file installed by hand. Only the fields that host needs to register an agent are checked.
- **Across hosts:** conversion translates only what both hosts' agents share, which is the name, description, instructions, model and effort. Any other key stops the conversion of that agent, because the other host cannot honor it, and dropping a restriction such as `tools` would produce a more privileged agent. Display and background-scheduling metadata (`color`, `background`, Codex `nickname_candidates`) is dropped with a warning instead.
- **Per agent:** a package that ships an agent's native definition for the target uses it instead of converting that agent; its other agents are still converted. A native definition is how an author keeps an agent whose settings do not convert.

Names follow Claude's runtime registration: `agents/review/security.md` named `internal-label` in plugin `kit` is `kit:review:internal-label`, and the Codex projection registers the same name. A Codex name `team:review` becomes `agents/team/review.md` named `review`, which Claude registers as `kit:team:review`.

A source model other than `inherit` requires an explicit mapping such as `--agent-model SOURCE=TARGET`. The converter does not select a supposedly equivalent model or check account availability.

After native Codex plugin installation, project agents from its installed root:

```sh
python3 scripts/plugin_port.py install-agents /path/to/installed/plugin --owner example@marketplace
python3 scripts/plugin_port.py install-agents /path/to/installed/plugin --owner example@marketplace --dry-run
python3 scripts/plugin_port.py install-agents --owner example@marketplace --remove
```

This supplemental command does not replace the plugin's marketplace or vendor its upstream source. It registers names as `plugin:agent`, matching Claude's plugin namespace. Rerun it after a native plugin update, and remove its owned copies when uninstalling that plugin. Run it again after a partial failure. It refuses local edits to its own copies, duplicate registered names, symlinks in place of its own files, and stale plans. A user's own agents, including ones a dotfile manager links in, are read only to detect name collisions and are never changed. File writes and its ownership receipt roll back together on a handled write failure. It never overwrites a user-managed agent, including with the marketplace installer's `--force` option.

`scripts/install-all` performs this projection automatically for selected Codex plugins after verifying their installed contents. It preflights mappings and collisions before native plugin mutations. The existing Claude installation path already loads native agent files. `--agent-model` is also accepted by `install-all`. Only selected plugins are reconciled; unselected agents remain unchanged. Installation uses POSIX `fcntl` locking and does not support native Windows; package conversion is independent of that lock. The native plugin transaction and agent projection are separate. If projection or the final installer receipt fails after native installation, the error reports that partial outcome. Resolve any reported local-agent conflict and rerun the same command. Already verified native plugins remain installed and are not rolled back.

Contracts are based on the [Codex custom-agent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Codex 0.163.0 role loader](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/agent-roles/src/loader.rs), and [Claude subagent documentation](https://code.claude.com/docs/en/sub-agents). Use a host version supporting those native formats and its subagent runtime. Installation does not enable feature flags or change provider, sandbox, or permission settings. Package validation, discovery and model invocation are separate checks.

Report fields include `schema_version`, `status`, `support_level`, `validation_summary`, `executable_surfaces`, `warnings`, `unsupported`, `preserved_only`, `mappings`, and `files_copied`.

Exit codes:

- `0`: success
- `2`: user input or unsupported conversion error
- `3`: validation failure
- `4`: required external validator unavailable

WHEN semantic loss would be unacceptable THEN you SHALL use `--mode strict`. WHEN publishing converted output THEN you SHALL inspect `.plugin-portability/report.json` for warnings, unsupported items, preserved-only items, executable/runtime surfaces, validation summaries, and file mappings. WHEN external validator parity is required THEN you SHALL run `validate` with `--require-external-validator`.

Local tests:

- `just test-plugin-port` runs deterministic converter and owned-agent installation tests.
- `PLUGIN_PORT_LIVE=1 PLUGIN_PORT_CLAUDE=1 just test-plugin-port-live` runs Claude CLI checks when `claude` is installed.
- `PLUGIN_PORT_LIVE=1 PLUGIN_PORT_CODEX=1 just test-plugin-port-live` runs Codex temp-marketplace checks when `codex` is installed.
- Set `PLUGIN_PORT_CODEX_BIN=/absolute/path/to/codex` to select a native executable when the `codex` wrapper chooses a different profile. The test confirms a unique skill marker from the temporary profile before registering or installing its fixture.
- Native agent lifecycle tests use disposable homes for both hosts. They require a positive profile marker before mutation, preserve an unrelated control plugin, and cover install, update, removal, and rejected replacements. Claude component discovery is checked through `plugin details`. Codex package loading and agent-file projection are checked separately; these tests do not claim model invocation.
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
scripts/install-all --include 'chatgpt-browser,project-harness' --exclude 'project-*'
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

Agentic Design & Evaluation replaces the `skill-auditor`, `split-testing`, and `friction-diagnostics` plugin identities. It retains the audit/comparison skill slugs and provides Self-Healing for observation capture and supported improvements. After the release reaches `DevGuyRash/agent-tooling@main`, run `scripts/install-all --include agentic-design-and-evaluation` with the normal canonical source. Verify the new package on both intended hosts before retiring the selected old installations.

For old installations in the user scope, the selected retirement commands are:

```sh
codex plugin remove skill-auditor@agent-tooling
codex plugin remove split-testing@agent-tooling
codex plugin remove friction-diagnostics@agent-tooling
claude plugin uninstall --scope user --keep-data skill-auditor@agent-tooling
claude plugin uninstall --scope user --keep-data split-testing@agent-tooling
claude plugin uninstall --scope user --keep-data friction-diagnostics@agent-tooling
```

For project/local installation, run the installer from the intended native project directory. The observed Claude CLI records its process working directory as `projectPath`, which can differ from the containing Git root or the local settings-file location. Inspect the actual installed scopes first; do not remove a separate project or local declaration by assumption. These commands select the three old user-scope identities and request retention of old Claude plugin data. Verify unrelated registrations and settings before and after retirement; the installation safeguard is not a general rollback or isolation guarantee for arbitrary later CLI commands. Removing an old marketplace entry alone does not uninstall its cached copy. Preserve saved observations. When running agents still call cached tools, disable the selected old plugin for new sessions before removing its cache. A fresh chat with the original objective, current state, completed effects and relevant evidence avoids carrying obsolete instructions forward through copied conversation history.

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

Docker Architect’s retired Compose and image launchers are preserved under `archived/plugins/docker-architect/`, together with their packaged binaries. They are no longer active artifact tasks. `scripts/rust-shim-template.sh` provides the reusable launcher form. The task’s `parameters.rust` selects the pinned release recipe; `scripts/build_rust_artifacts.py` prepares two independent builds and compares their bytes before delivery. The preserved Docker Architect deliveries target Linux x86-64.

`scripts/package_skills.py` retains the existing packaging command names as adapters over the task engine. `stage-host` and `dist-refresh` synchronize selected Rust tasks; verification commands check their receipts without rebuilding. `sync-artifacts` imports prepared outputs only with matching task receipts and source identities. `vendor` operates on direct-copy tasks. The manifest, receipt format and publication logic have one maintained owner.

Setup flags remain documented by `scripts/setup.sh` and `scripts/maintenance.sh`. Plugin installation uses the explicit installer described above.

