# Scenario Examples

Load this file when you want concrete end-to-end patterns.

## 1) Personal tool, one platform, clone-and-run

Choose:
- architecture: `committed-dist`
- dist storage: `git`
- CI mode: `just`

Why:
- simplest workflow
- minimal infrastructure
- okay when binaries are small and infrequently updated

## 2) Small-team internal CLI, outputs growing over time

Choose:
- architecture: `committed-dist`
- dist storage: `git-lfs`
- CI mode: `just` or `direct`

Why:
- keeps clone-and-run ergonomics
- slows normal git history growth
- still works well for a small team

## 3) Public open-source CLI with Linux, Windows, and macOS deliverables

Choose:
- architecture: `general` or `local-dist`
- dist storage: `artifacts`
- CI mode: `direct`
- release overlay: on

Why:
- source history stays clean
- CI can publish per-platform outputs
- easier to evolve release packaging independently from local development

## 4) Polyglot monorepo with app plus service

Choose:
- architecture: `general` or `local-dist`
- dist storage: `none`
- CI mode: `direct`

Why:
- monorepos benefit from per-component plus aggregate recipes
- CI usually needs explicit setup and sequencing

## 5) Repo with no scripts, no workflows, no examples

Choose:
- architecture: `general`
- dist storage: `none`
- CI mode: `none`

Why:
- start with a placeholder harness
- do not over-assume lifecycle commands
- refine after one grounded pass through the repo

## 6) Agent skill that must be runnable after clone

Choose:
- architecture: `committed-dist` or `cross-os-dist`
- dist storage: `git` for tiny outputs, `git-lfs` if growth matters
- CI mode: optional

Why:
- skills often benefit from self-contained execution
- committed deliverables can matter more than repo purity
