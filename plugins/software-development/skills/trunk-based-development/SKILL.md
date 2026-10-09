---
name: trunk-based-development
description: Use when integration strategy needs mergeable slices, short branches, safe incomplete work, or divergence recovery. Excludes routine Git/PR operations, CI, releases, and governance.
---

# Trunk-Based Development

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Integration stays frequent when each change can reach a healthy shared trunk on its own. Repository policy is authoritative: its default branch, contribution guidance, branch protection and required checks, release model, deployment coupling, and merge, rebase, squash, or queue behavior decide the flow, and trunk-based development works with direct integration, short-lived reviewed branches, and merge queues alike.

You SHALL integrate through the project's required review, signed commits, status checks, and protected branches.

- Frequent integration is the goal; daily merges and few active branches are team diagnostics, not timers or quotas.
- An increment is the smallest outcome that can merge while trunk stays buildable, testable, and safe for its normal deployment model; a slicing plan orders the increments with their dependency edges, compatibility constraints, safety mechanism for incomplete behavior, pre-integration evidence, and cleanup conditions.
- A good increment builds and tests on its own, serves one reviewable purpose, stays backward compatible with adjacent deployed or in-flight code, is small enough to integrate before assumptions drift, and has a recovery route its dependents allow: revert while nothing later depends on it, otherwise containment or a small forward repair.
- Keep incomplete work safe by the least costly means that preserves trunk's normal behavior: a compatible seam or branch by abstraction for structural work; an inactive path or short-lived flag for releasable software, not for an unreleased library, local tool, or simple compatible slice that gains nothing from runtime gating; additive schema or API changes before consumers migrate; vertical slices when each can deliver usable behavior.
- Transitional code and flags have a recorded removal condition.
- Before reslicing or updating a diverged branch, preserve the user's changes, including uncommitted worktree state, and determine its dependencies; reslice or update against current trunk before adding work.
- When integrated code breaks trunk, check what depends on it, then choose a small forward repair if it is clear and verifiable, a revert if it invalidates no dependent work, or containment if neither is safe yet.
- A push or merge response does not show that integration succeeded; the repository's checks and trunk's resulting state do.

Read [small-batch patterns](references/small-batch-patterns.md) when a feature, refactor, or migration looks too large to merge safely in one short-lived line of work.
