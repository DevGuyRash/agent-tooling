---
name: project-harness
description: >-
  Detects repo languages, frameworks, task runners, distribution shape, and CI
  surface, then scaffolds or updates a repo-level harness: justfile, GitHub
  Actions CI/dist workflows, .gitignore/.gitattributes support files, and
  local state under .local/harness/. Use when the task is to bootstrap,
  standardize, update, or run a project command surface without rewriting the
  build system internals themselves.
license: MIT
metadata:
  author: DevGuyRash
  version: "2.2.0"
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
- how should a repo with no existing examples still get a usable starting harness?

## What this skill owns

This skill owns the repo-level wrapper surface:
- `justfile`
- `.github/workflows/ci.yml`
- `.github/workflows/release-cross-os.yml`
- `.gitignore` additions related to `.local/` and `dist/`
- `.gitattributes` additions for `dist/**` when Git LFS is selected
- `.local/harness/state.json`
- `.local/harness/render/*` candidate files

This skill does **not** rewrite:
- `Cargo.toml`
- `package.json`
- `pyproject.toml`
- `pom.xml`
- `go.mod`
- existing build manifests in general

## Default workflow

1. Detect the repo shape.

```bash
python <skills-file-root>/scripts/project_harness.py detect /path/to/repo --pretty
```

2. Choose three axes:
- architecture: `general`, `local-dist`, `committed-dist`, or `cross-os-dist`
- dist storage: `none`, `git`, `git-lfs`, or `artifacts`
- CI mode: `none`, `just`, or `direct`

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

### When the repo has **no** examples

Do not fail. Generate a minimal canonical harness with placeholder recipes and a
comment block that explains what to replace.

Default behavior for no-example repos:
- generate a `justfile`
- keep CI mode at `none` unless setup is truly obvious
- leave distribution mode at `general` unless the repo already shows binary/dist intent
- store decisions and warnings in `.local/harness/state.json`

Load `<skills-file-root>/references/generic-harnesses.md` for the full no-example policy.

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
- `direct`: CI installs toolchains, runs bootstrap steps directly, then explicit checks

Use `direct` for monorepos, matrices, or polyglot repos.
Use `just` for smaller repos where `just ci` should stay the source of truth.

Load `<skills-file-root>/references/ci-workflows.md` for workflow quality rules,
runner notes, and open-source versus private-repo tradeoffs.

## Existing-file policy

Managed files are overwritten only when absent or already marked as managed.
Unmanaged targets are never force-merged blindly; candidate files are written
instead under `.local/harness/render/`.

Load `<skills-file-root>/references/existing-files.md` before changing a repo
with an existing `justfile`, workflow set, or custom dist layout.

## References to load on demand

Load these only when relevant:
- `<skills-file-root>/references/detection.md`
- `<skills-file-root>/references/selection.md`
- `<skills-file-root>/references/distribution-strategies.md`
- `<skills-file-root>/references/generic-harnesses.md`
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
- `<skills-file-root>/assets/workflow-release-cross-os.yml.tpl`
- `<skills-file-root>/assets/gitattributes-lfs.tpl`

Generalized examples:
- `<skills-file-root>/assets/just-no-example.just.tpl`
- `<skills-file-root>/assets/workflow-release-assets-cross-os.yml.tpl`

## Bundled scripts

- `<skills-file-root>/scripts/project_harness.py`
- `<skills-file-root>/scripts/validate_skill.py`
- `<skills-file-root>/scripts/selftest_project_harness.py`

## Validation

```bash
python <skills-file-root>/scripts/validate_skill.py <skills-file-root> --pretty
python <skills-file-root>/scripts/validate_skill.py <skills-file-root> --pretty --smoke
```
