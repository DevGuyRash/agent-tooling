# Selection: Architecture, Storage, CI, and Change Detection

Load this file after detection.

There is no single "best" harness. Pick the harness axes deliberately.

When signals are mixed, choose the more reversible axis value first.
The goal is a harness that can be refined safely, not one that looks maximally
complete on the first pass.

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
- best fallback when the distribution story is only implied

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

Do not choose this from weak evidence alone.

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

Prefer this over speculative committed outputs when the build is clear but the
repository storage policy is not.

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

Keep the first choice reversible:
- single-job direct CI is the default direct shape
- split direct CI is an explicit overlay, not an automatic promotion
- path filters stay manual and fail closed when root workspace surfaces exist

## Axis 4: Change detection

### `none`

Use when:
- the repo's build is cheap enough that unconditional CI is simpler
- the repo does not have a distinct expensive build lane yet
- you want the most obvious workflow behavior first

Result:
- generated CI always runs its normal jobs
- no extra detection job is inserted
- best default for new harnesses

### `git-diff`

Use when:
- the repo explicitly opted into split direct CI
- there is a distinct `build` job that is materially more expensive than lint/test
- path-based change detection is good enough and easier to explain than custom hashing

Result:
- generate a lightweight `detect-changes` job ahead of `build`
- gate `build` on repo-relative changed-path patterns derived from the promoted runnable surfaces
- keep `lint` and `test` unconditional unless the repo asks for a more custom overlay elsewhere

Current generated scope:
- supported only for `direct` CI with `--ci-layout split`
- emitted as an opt-in overlay, not a default
- intended for expensive build lanes, not as a generic skip-everything mechanism

## Mixed-signal rule

If one axis is well supported and another is weak, commit only the supported one.

Examples:
- clear lifecycle plus unclear dist story -> generate commands, keep architecture at `general`
- clear commands plus unsafe trigger boundaries -> generate CI without path filters
- obvious local harness plus ambiguous CI bootstrap -> render the `justfile`, keep CI at `none`
- broad raw detection plus only one promoted runnable surface -> keep CI and recipes narrow instead of promoting every detected subtree

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
- `none` first, then `git-diff` only if build minutes become material

### Agent skill that must be self-contained

Usually:
- `committed-dist` or `cross-os-dist`
- `git` for very small outputs, `git-lfs` when growth matters
- `just` or `none`, depending on whether GitHub Actions is part of the delivery story
- `none` unless the skill's build lane is distinct and expensive enough to justify `git-diff`

### Open-source CLI or shared public project

Usually:
- `general` or `local-dist`
- `artifacts`
- `direct`
- `none` first, then `git-diff` for an explicit expensive build lane
- add a cross-OS dist/release overlay only if binaries are a public deliverable

### Unknown repo with no examples

Usually:
- `general`
- `none`
- `none` or `artifacts`
- generate placeholder recipes first, then refine
