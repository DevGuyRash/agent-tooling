# Generic Harnesses for Repos with No Examples

Load this file when detection finds little or nothing.

The harness still needs to be useful even when the repo does not already tell
you how it wants to work.

## Default policy

When no clear build surface is present:
- generate a canonical `justfile`
- keep CI mode at `none`
- keep distribution at `general`
- insert a guidance comment block
- write state and warnings so the repo can be refined later

That produces a usable starting point instead of a refusal.

## Canonical recipe meanings

Use these meanings consistently:
- `bootstrap`: install project dependencies and prepare the working tree
- `fmt`: rewrite source into the preferred style
- `fmt-check`: verify formatting without rewriting
- `lint`: static checks beyond formatting
- `test`: validation of behavior
- `build`: ordinary build output
- `release`: optimized or distributable output
- `dist`: stage distributable payloads
- `clean`: remove generated state
- `ci`: the minimal required checks for a pull request
- `dev`: the main interactive developer loop

## Recipe descriptions and examples

The generated `justfile` should explain itself even before someone opens the skill docs.

WHEN you generate a public recipe THEN you SHALL place a one-line description comment directly above it.
WHEN a recipe is scoped to a component, platform, or distribution surface THEN you SHALL say so in the description.
WHEN the repo still relies on placeholders or has a non-obvious lifecycle THEN you SHOULD add a short header block with a few example invocations.
You SHALL NOT fill the file with vague comments such as `# Build the project` when the recipe can describe the actual scope or effect more precisely.

Good description examples:
- `# Install dependencies, tooling, and local prerequisites for normal development`
- `# Compile only backend in the default build profile`
- `# Run static analysis and policy checks only for frontend`
- `# Remove staged dist payloads without touching source files`

Good header example:

```text
# Usage examples:
#   just bootstrap         # install local prerequisites and tooling
#   just ci                # run the pull-request verification surface
#   just dist              # compile release outputs and stage them under dist/
```

## How to infer a first harness without examples

Look for weak signals, not only explicit scripts:
- README commands
- docs snippets
- lockfiles
- language markers
- folder names like `cmd/`, `src/`, `app/`, `server/`, `cli/`, `packages/`
- existing workflow files
- Dockerfiles or compose files

If the signal is weak, prefer placeholders plus notes over fake certainty.

## Aggressive automation with guardrails

Extrapolate when the repo gives you enough evidence to be useful.
Do not wait for a perfect example if the build surface is already obvious.

Good extrapolation targets:
- canonical recipe names
- package-manager install commands when manifest plus lockfile agree
- ordinary CI for a single obvious project
- candidate renders for unmanaged incumbent files

Stop short when the missing piece would change repository policy, not just one command.
Examples:
- do not invent a committed dist story from a weak binary hint
- do not infer path filters from folder names alone
- do not turn ambiguous docs snippets into authoritative release steps

When confidence is partial:
- generate the reversible surface
- attach warnings and notes
- leave higher-risk surfaces off until the repo is clearer
- do not create empty per-component scaffolding for weak detections the agent is unlikely to touch

## When to generate CI anyway

Generate CI only when setup is obvious enough that a first run is likely to
succeed.

Good examples:
- a single Python project with obvious `pyproject.toml`
- a single Node project with scripts and lockfile
- a single Rust crate

Bad examples:
- repo with only docs and source directories
- polyglot repo without any scripts or manifests tying it together
- monorepo folders with inconsistent conventions and no top-level owner

## Minimal placeholder policy

A placeholder harness is acceptable when it is explicit.

It should:
- say no native build surface was detected
- keep recipe names canonical
- describe what each placeholder recipe is meant to represent
- make missing commands obvious
- avoid pretending to know the package manager or test runner

The generated comment block is part of the design, not an error.

Use placeholders as a deliberate fallback when you can name the lifecycle stage
but cannot defend the exact command.

## Refinement path

After the first generic harness exists:
1. replace placeholder recipes with the real lifecycle commands
2. turn CI on only after bootstrap and checks are stable
3. add `local-dist`, `committed-dist`, or `cross-os-dist` only when the repo
   truly has a distribution story
