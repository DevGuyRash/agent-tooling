---
name: Project Harness
description: >-
  Detects repo languages, frameworks, task runners, distribution shape, and CI
  surface, then scaffolds or updates a repo-level harness: justfile, GitHub
  Actions CI/dist workflows, .gitignore/.gitattributes support files, and
  local state under .local/harness/. Use when the task involves:
  (1) Bootstrapping a new or existing repo with a standardized command surface,
  (2) Creating or updating a justfile with build, test, lint, fmt, ci, dev,
  or dist recipes, (3) Scaffolding GitHub Actions CI or distribution workflows,
  (4) Configuring .gitignore, .gitattributes, or Git LFS for a project,
  (5) Standardizing or updating a project command surface without rewriting
  build system internals, or (6) Any task requiring repo-level harness
  scaffolding or project command surface management.
license: MIT
metadata:
  author: DevGuyRash
  version: "2.6.0"
  category: development
compatibility: >-
  Requires Python 3.11+ to run the bundled CLI. Optional: just, git, git-lfs,
  gh, Docker, and language-specific toolchains. Works best on Linux, macOS,
  and Windows when bash, Git Bash, or WSL is available for POSIX-shell recipes.
---

# Project Harness

This skill creates or updates a repo-wide command harness without trying to
rewrite the repo's package manifests, lockfiles, or build internals.

It is meant to answer questions like:
- how should this repo expose bootstrap, build, test, lint, fmt, ci, dev, and dist?
- should `dist/` stay local, be committed, be tracked with Git LFS, or come only from CI?
- should CI call `just ci`, mirror commands directly, or stay off until the repo is better defined?
- how should a monorepo expose both per-component and aggregate recipes?
- when should a contributor-heavy repo split CI into stable `lint`, `test`, and `build` jobs?
- how should a repo with no existing examples still get a usable starting harness?

## What this skill owns

This skill owns the repo-level wrapper surface:
- `justfile`
- `.github/workflows/ci.yml`
- `.github/workflows/release-cross-os.yml`
- `githooks/pre-push` when the selected architecture uses committed dist outputs
- `.gitignore` additions related to `.local/` and `dist/`
- `.gitattributes` managed section with broad text/EOL and binary defaults, plus `dist/**` Git LFS tracking when selected
- `.local/harness/state.json`
- `.local/harness/render/*` candidate files

This skill does **not** rewrite:
- `Cargo.toml`
- `package.json`
- `pyproject.toml`
- `pom.xml`
- `go.mod`
- existing build manifests in general

This skill also does **not** own governance enforcement such as required checks,
CODEOWNERS reconciliation, or branch/ruleset policy. Keep those in a governance
tooling surface such as `gitops-workflow`.

Repo-owned Git hooks are a local convenience overlay, not the authoritative enforcement surface. Keep CI and branch governance authoritative even when this skill emits `githooks/pre-push` and a `hooks-install` recipe.

## Justfile quality bar

The generated `justfile` is a user interface, not just a dump of commands.

WHEN this skill generates a public recipe THEN you SHALL place a one-line description comment directly above it.
WHEN the recipe is scoped to a component, platform, or distribution surface THEN you SHALL name that scope in the description.
WHEN the repo has non-obvious operational surfaces such as packaging, dist refresh, hooks, or Docker workflows THEN you SHOULD add a short header comment block with two or three example invocations.
You SHALL NOT rely on bare labels such as "Run linters" or "Build the project" when the repo surface is specific enough to describe more precisely.

Preferred description style:
- one line
- outcome-first
- precise about scope and side effects
- written so it still reads cleanly in `just --list`

Good examples:
- `# Install dependencies, tooling, and local prerequisites for normal development`
- `# Compile only crates/mpcr in the default build profile`
- `# Compile release outputs and stage them into dist/ for local packaging`
- `# Remove staged dist payloads without touching source files`

Weak examples:
- `# Run linters`
- `# Build the project`
- `# Clean`

## Default workflow

1. Detect the repo shape.

```bash
python <skills-file-root>/scripts/project_harness.py detect /path/to/repo --pretty
```

2. Choose the command and CI axes:
- architecture: `general`, `local-dist`, `committed-dist`, or `cross-os-dist`
- dist storage: `none`, `git`, `git-lfs`, or `artifacts`
- CI mode: `none`, `just`, or `direct`
- CI shape: single-job direct CI by default, with `--ci-layout split` as an opt-in contributor-scale overlay
- change detection: `none` by default, with `--change-detection git-diff` as an opt-in build-lane overlay for split direct CI
- path filters: manual opt-in only when component ownership is explicit

3. Preview candidate files without touching managed targets.

```bash
python <skills-file-root>/scripts/project_harness.py render /path/to/repo --pretty
```

4. Apply the managed update.

```bash
python <skills-file-root>/scripts/project_harness.py update /path/to/repo --pretty
```

`update` writes managed files by default. Use `render` when you want a dry preview.

5. Bootstrap or run through the harness.

```bash
python <skills-file-root>/scripts/project_harness.py bootstrap /path/to/repo
python <skills-file-root>/scripts/project_harness.py run /path/to/repo test
python <skills-file-root>/scripts/project_harness.py doctor /path/to/repo --pretty
```

## Default decision rules

### When the repo already has a clear build surface

Detect and mirror it first.

Examples:
- package scripts -> generate matching `just` recipes
- Cargo binaries -> generate `build`, `release`, and dist staging candidates
- Makefile or Taskfile -> preserve them, map canonical targets where obvious
- monorepo/workspace -> emit both per-component recipes and aggregate top-level recipes

Also generate recipe descriptions that explain what each recipe does, not just its canonical name.

### When the repo has **no** examples

Do not fail. Generate a minimal canonical harness with placeholder recipes and a
comment block that explains what to replace.

Default behavior for no-example repos:
- generate a `justfile`
- keep CI mode at `none` unless setup is truly obvious
- leave distribution mode at `general` unless the repo already shows binary/dist intent
- store decisions and warnings in `.local/harness/state.json`
- include recipe descriptions plus a short header block that shows how the placeholder harness is meant to be used

Load `<skills-file-root>/references/generic-harnesses.md` for the full no-example policy.
Load `<skills-file-root>/references/extrapolation-protocol.md` when you need the
full detect -> infer -> render -> stop protocol for partially explicit repos.

## Distribution choices

Use three separate questions.

### 1) Architecture

- `general`: command wrapper only, no dist section
- `local-dist`: stage artifacts into ignored `dist/`
- `committed-dist`: keep `dist/` in git for clone-and-run workflows
- `cross-os-dist`: stage per-platform outputs into `dist/<os>-<arch>/`

### 2) Dist storage

- `none`: there is no committed dist story yet
- `git`: keep `dist/` in normal git history
- `git-lfs`: keep `dist/` committed but move payloads out of normal git blobs
- `artifacts`: prefer CI artifacts or release assets instead of committed outputs

### 3) Release overlay

The generated cross-OS workflow is an artifact-oriented overlay. For true
GitHub Release assets, start from
`<skills-file-root>/assets/workflow-release-assets-cross-os.yml.tpl`.

## CI choices

- `none`: do not generate CI yet
- `just`: CI installs toolchains plus `just`, runs `just bootstrap`, then `just ci`
- `direct`: CI installs toolchains, runs bootstrap steps directly, then explicit checks; contributor-heavy repos may opt into stable `lint`, `test`, and `build` jobs

Use `direct` for monorepos, matrices, or polyglot repos.
Use `just` for smaller repos where `just ci` should stay the source of truth.
Use split direct CI only when a repo explicitly opts into it and stable per-job checks are more valuable than preserving a single `ci` check surface.
Keep change detection at `none` unless the repo has an expensive, distinct `build` lane worth gating. The generated `git-diff` overlay currently targets split direct CI only.
Keep path filters manual and explicit; do not infer them unless the repo truly has stable ownership boundaries.

Load `<skills-file-root>/references/ci-workflows.md` for workflow quality rules,
runner notes, contributor-scale guidance, governance handoff notes, and open-source versus private-repo tradeoffs.

When examples do not match the repo exactly:
- explore the actual repo first
- infer from strong signals before weak ones
- prefer generated defaults when the evidence supports them
- prefer placeholders, candidate renders, or `none` when the safety boundary is unclear
- treat example-only assets as patterns, not as repo truth
- detect broadly, but only promote runnable repo-owned surfaces into generated recipes and workflows
- leave weak nested surfaces in notes and state instead of turning them into decorative scaffolding

## Existing-file policy

Managed files are overwritten only when absent or already marked as managed.
Unmanaged targets are never force-merged blindly; candidate files are written
instead under `.local/harness/render/`.

`.gitattributes` is managed by section instead of by whole file.
WHEN this skill updates `.gitattributes` THEN you SHALL preserve human-authored rules outside the project-harness managed section.
WHEN `.gitattributes` already exists without a project-harness section THEN you SHALL insert the managed section after leading comments and blank lines so later repo-specific rules can override the baseline.
WHEN `.gitattributes` already contains a project-harness section THEN you SHALL replace only that section.

Load `<skills-file-root>/references/existing-files.md` before changing a repo
with an existing `justfile`, workflow set, or custom dist layout.

## References to load on demand

Load these only when relevant:
- `<skills-file-root>/references/detection.md`
- `<skills-file-root>/references/selection.md`
- `<skills-file-root>/references/distribution-strategies.md`
- `<skills-file-root>/references/generic-harnesses.md`
- `<skills-file-root>/references/extrapolation-protocol.md`
- `<skills-file-root>/references/scenarios.md`
- `<skills-file-root>/references/ci-workflows.md`
- `<skills-file-root>/references/existing-files.md`
- `<skills-file-root>/references/docker-workspaces.md`
- `<skills-file-root>/references/makefile-migration.md`
- `<skills-file-root>/references/state-and-recovery.md`
- `<skills-file-root>/references/language-rust.md`
- `<skills-file-root>/references/language-python.md`
- `<skills-file-root>/references/language-javascript.md`
- `<skills-file-root>/references/language-compiled.md`
- `<skills-file-root>/references/language-other.md`

## Bundled assets

Operational templates:
- `<skills-file-root>/assets/just-general.just.tpl`
- `<skills-file-root>/assets/just-local-dist.just.tpl`
- `<skills-file-root>/assets/just-committed-dist.just.tpl`
- `<skills-file-root>/assets/just-cross-os-dist.just.tpl`
- `<skills-file-root>/assets/workflow-ci-just.yml.tpl`
- `<skills-file-root>/assets/workflow-ci-direct.yml.tpl`
- `<skills-file-root>/assets/workflow-ci-direct-split.yml.tpl`
- `<skills-file-root>/assets/workflow-release-cross-os.yml.tpl`

Generalized examples:
- `<skills-file-root>/assets/just-no-example.just.tpl`
- `<skills-file-root>/assets/workflow-ci-direct-component-paths.yml.tpl`
- `<skills-file-root>/assets/workflow-release-assets-cross-os.yml.tpl`
- `<skills-file-root>/assets/gitattributes-baseline.tpl`

## Bundled scripts

- `<skills-file-root>/scripts/project_harness.py`
- `<skills-file-root>/scripts/validate_skill.py`
- `<skills-file-root>/scripts/selftest_project_harness.py`

## Validation

```bash
python <skills-file-root>/scripts/validate_skill.py <skills-file-root> --pretty
python <skills-file-root>/scripts/validate_skill.py <skills-file-root> --pretty --smoke
```
