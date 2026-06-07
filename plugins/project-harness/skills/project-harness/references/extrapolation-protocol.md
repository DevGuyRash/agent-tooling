# Extrapolation Protocol

Load this file when the repo shape is only partially explicit and you need to
generalize from evidence instead of copying a canned example.

The harness should extrapolate aggressively when the evidence supports it, but
it should still stop short of fake certainty.

## Decision flow

Work through the repo in this order:
1. detect strong signals
2. detect weak signals
3. identify red flags
4. decide which surfaces are safe to generate
5. downgrade uncertain surfaces to placeholders, candidate-only output, or `none`

Do not decide from one clue in isolation.
Use multiple agreeing signals before you claim a runnable lifecycle.

## Signal classes

### Strong signals

Strong signals are enough to justify generation when they agree:
- package manifests with matching lockfiles
- obvious task runners such as `justfile`, `Makefile`, or `Taskfile`
- explicit package scripts
- clear workspace manifests
- existing CI workflows showing a stable lifecycle
- known language build manifests such as `Cargo.toml`, `pyproject.toml`, `pom.xml`, or `go.mod`
- an existing `dist/` layout with a clear repository policy around it

### Weak signals

Weak signals support a decision but should not carry it alone:
- README command snippets
- docs fragments
- framework hints
- conventional folder names such as `cmd/`, `src/`, `server/`, `app/`, or `packages/`
- one-off shell scripts
- Dockerfiles and compose files

### Red flags

Red flags force a more reversible choice even when some good signals exist:
- conflicting package managers or toolchains
- multiple plausible bootstrap surfaces with no clear owner
- root workspace manifests plus nested components that would complicate path filtering
- unmanaged incumbent workflows or task runners with unclear ownership
- partial examples that show checks but not bootstrap/install steps
- distribution hints without an explicit repository storage story

## Surface-by-surface rules

Before any generated surface is emitted:
- detect components broadly
- promote only repo-owned surfaces with strong enough evidence
- require a defendable runnable lifecycle before a surface can affect recipes, CI, or release output
- keep weak detections visible in notes and state instead of generating decorative sub-surfaces

### `justfile`

Generate a real `justfile` when:
- strong signals identify the lifecycle commands, or
- the repo has enough weak signals to justify canonical placeholder recipes

Use placeholders when:
- you can name the lifecycle stages but not the actual commands

Treat recipe descriptions as part of the generated interface, not optional garnish.
WHEN you infer or promote a recipe THEN you SHALL infer or supply a description that explains the recipe's scope and expected effect.
WHEN the recipe is component-prefixed or affects packaging, dist, hooks, or CI THEN you SHALL name that scope explicitly.
WHEN longer guidance would clutter the recipe list THEN you SHOULD keep the recipe description to one line and move examples into a short header comment block.

Do not invent:
- package-manager-specific install commands
- test runners
- release packaging steps
when the evidence does not support them.

### Ordinary CI

Generate ordinary CI when:
- bootstrap and checks are likely to run successfully on a first pass
- the lifecycle is explicit enough that CI will not be mostly placeholders

Keep CI at `none` when:
- bootstrap is ambiguous
- the repo is still mostly placeholder-driven
- another CI system is clearly authoritative

### Split direct CI

Use split direct CI only when:
- the repo explicitly opts into it, and
- there is a real need for stable `lint`, `test`, and `build` checks

Do not promote a repo into split CI automatically just because it is large.
Preserve the single `ci` check by default unless the user or stored selection
has chosen the split shape.

### Component path filters

Allow component path filters only when:
- ownership boundaries are explicit
- the tracked build surfaces are nested cleanly under those components
- no root-level component or workspace manifest would change generated CI behavior

Fail closed when:
- a root workspace manifest exists
- shared bootstrap files live at the repo root
- component ownership is only implied, not explicit

### Dist and release overlays

Generate dist or release overlays only when:
- the repo has an obvious binary or distributable output story, and
- the storage model is explicit enough to choose `none`, `git`, `git-lfs`, or `artifacts`

Prefer `general` plus notes over a speculative dist section.

## Reversible-default policy

When signals are mixed, choose the more reversible option:
- prefer `general` over a committed dist architecture
- prefer `none` or `artifacts` over speculative committed outputs
- prefer `just` or single-job `direct` over split CI
- prefer candidate-only output over overwriting unmanaged files
- prefer placeholders plus notes over invented commands

## Generated versus example-only assets

Treat the asset classes differently:

Generated defaults:
- may be rendered automatically when the evidence is strong enough

Generated opt-in overlays:
- may be rendered only after an explicit choice such as split CI or a release overlay

Example-only assets:
- are illustrative patterns, not inferred repo truth
- must be adapted before use
- should never be treated as automatic evidence about a downstream repo

## Stop conditions

Stop short of a confident generated surface when:
- the inferred command would be more guess than evidence
- the generated CI trigger would be unsafe if skipped
- the repo already has unmanaged artifacts that the harness does not own
- the distribution story would commit or publish outputs on a weak signal alone

When you stop, leave behind:
- a candidate render if appropriate
- warnings
- notes that explain what evidence was missing

That is still a valid harness outcome.
