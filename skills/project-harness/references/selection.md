# Selection: Architecture, Storage, and CI

Load this file after detection.

There is no single "best" harness. Pick three axes deliberately.

## Axis 1: Harness architecture

### `general`

Use when:
- the repo mainly needs a unified command surface
- there is no staged binary distribution yet
- the repo may still be early or poorly defined

Result:
- canonical lifecycle recipes only
- no dist section
- best default for no-example repos

### `local-dist`

Use when:
- the repo stages outputs into `dist/`
- consumers are expected to build locally after clone
- `dist/` should remain ignored

Result:
- add `dist`, `clean-build`, and `clean-dist`
- keep `dist/` ignored in `.gitignore`

### `committed-dist`

Use when:
- consumers need clone-and-run behavior on one platform or a small platform set
- outputs are small enough, stable enough, or important enough to keep in the repo
- the repo is an internal tool, an agent skill, a config repo, or a small-team utility

Result:
- `dist/` belongs to the repository
- `clean-build` must preserve committed outputs
- choose normal git versus Git LFS separately

### `cross-os-dist`

Use when:
- Linux, macOS, and Windows outputs are all first-class
- committed per-platform outputs or CI-built per-platform artifacts matter
- the repo needs a clear `dist/<os>-<arch>/` story

Result:
- stage into `dist/<platform-id>/`
- usually pair with a cross-OS workflow
- often pair with `artifacts` or `git-lfs`

## Axis 2: Dist storage

### `none`

Use when:
- there is no committed distribution plan yet
- the repo is source-first

### `git`

Use when:
- binaries are small
- update frequency is low
- repo size growth is acceptable
- clone-and-run simplicity matters more than history cleanliness

### `git-lfs`

Use when:
- `dist/` still belongs in the repo model
- normal git history growth is becoming a problem
- binary outputs are larger or churn more often

Use this mainly with `committed-dist` or `cross-os-dist`.

### `artifacts`

Use when:
- outputs should come from CI or Releases instead of the default clone
- the repo is open source or widely shared
- binaries are large or frequently updated
- you want to keep normal git history source-first

## Axis 3: CI mode

### `none`

Use when:
- the repo has no obvious lifecycle yet
- another CI system is authoritative
- you only want local harness generation first

### `just`

Use when:
- the repo is small enough that `just ci` should stay the source of truth
- Linux-only CI is acceptable at first
- local and CI symmetry matters most

### `direct`

Use when:
- the repo is polyglot
- the repo is a monorepo or workspace
- the workflow needs matrices, artifacts, or split jobs
- you want CI logic to stay explicit instead of hidden behind one command

## Recommended combinations

### Personal repo or single-user internal tool

Usually:
- `general` or `committed-dist`
- `git`
- `just`

### Small team internal tool

Usually:
- `local-dist` or `committed-dist`
- `git` or `git-lfs`
- `just` for small repos, `direct` for monorepos

### Agent skill that must be self-contained

Usually:
- `committed-dist` or `cross-os-dist`
- `git` for very small outputs, `git-lfs` when growth matters
- `just` or `none`, depending on whether GitHub Actions is part of the delivery story

### Open-source CLI or shared public project

Usually:
- `general` or `local-dist`
- `artifacts`
- `direct`
- add a cross-OS dist/release overlay only if binaries are a public deliverable

### Unknown repo with no examples

Usually:
- `general`
- `none`
- `none` or `artifacts`
- generate placeholder recipes first, then refine
