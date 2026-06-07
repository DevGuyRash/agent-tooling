# Distribution Strategies

Load this file when the question is really about distribution policy, not just
syntax.

The right answer depends on who consumes the repo, how often outputs change,
and how much git history growth you can tolerate.

## Strategy 1: Source only

Shape:
- source code only
- no committed `dist/`
- users bootstrap or build locally

Best for:
- libraries
- early-stage repos
- teams where every user already has the toolchain

Recommended harness:
- architecture: `general` or `local-dist`
- dist storage: `none`
- CI mode: `just` or `direct`

## Strategy 2: Commit `dist/` in normal git

Shape:
- source plus committed outputs
- clone-and-run is the goal

Best for:
- personal tooling
- config repos
- small internal utilities
- small agent-skill binaries

Tradeoff:
- git history accumulates every binary revision
- repo cloning stays simple, but history and fetch size grow over time

Recommended harness:
- architecture: `committed-dist` or `cross-os-dist`
- dist storage: `git`

## Strategy 3: Commit `dist/` but track it with Git LFS

Shape:
- `dist/` stays part of the repository contract
- payloads move out of normal git blob history

Best for:
- clone-and-run repos whose outputs have become too large or too noisy for normal git
- small-team repos that still want committed deliverables

Tradeoff:
- consumers need Git LFS support when interacting with the repo normally
- archive/download expectations must be checked carefully
- bandwidth/storage policy starts to matter

Recommended harness:
- architecture: `committed-dist` or `cross-os-dist`
- dist storage: `git-lfs`

## Strategy 4: CI artifacts or Release assets only

Shape:
- repository stays source-first
- CI builds and uploads outputs

Best for:
- open-source CLIs
- public repos
- multi-platform releases
- large or fast-changing binaries

Tradeoff:
- clone-and-run is gone unless a bootstrap step downloads artifacts
- more CI/release plumbing is required

Recommended harness:
- architecture: `general` or `local-dist`
- dist storage: `artifacts`
- add the cross-OS overlay when binaries are a deliverable

## Cross-OS notes

When the repo must ship Linux, Windows, and macOS outputs, answer these first:
- do all three belong in the repo, or only in CI artifacts?
- is macOS arm64 enough, or is macOS x64 also required?
- are you okay with native-per-runner builds, or do you need explicit cross compilation?

Prefer native-per-runner builds for the first version of the harness.
Cross compilation is a follow-on concern and should be introduced only when the
repo already has a proven target matrix.

## Heuristics by project type

### Single-user or tiny team

Bias toward simplicity:
- committed outputs are often okay
- repo growth is usually less painful than extra infrastructure

### Internal multi-repo team tool

Bias toward balance:
- small outputs may still live in git
- larger outputs usually justify Git LFS or artifacts

### Public open-source project

Bias toward source-first history:
- artifacts or releases are usually better than committed binaries
- CI minutes/storage and release ergonomics matter more than clone-and-run

## History-growth rule of thumb

As binary size and update frequency rise, prefer this progression:
- `git`
- `git-lfs`
- `artifacts`

Do not jump straight to the most complex option unless the repo already shows
that simpler options are failing.
