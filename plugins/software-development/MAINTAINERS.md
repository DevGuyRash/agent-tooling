# Maintainer Notes

## Release gates

Run the plugin contract tests, each skill validator, the repository plugin audit, strict dual-host conversion and round trips, converter tests, install-all tests, and the Rust panic-audit test suite. Inspect the converted reports for semantic loss; structural success alone is insufficient.

Trigger evaluation compares the no-plugin baseline, the prior Rust or GitOps behavior where relevant, and the new composition. Score correctness, repository-convention preservation, verification quality, unnecessary work, unsupported mandates, and active-context cost. Exact phrasing is not a pass condition.

Installed-host acceptance uses fresh Codex and Claude tasks with the full agent-tooling marketplace visible. Confirm all 26 skills remain discoverable, explicit invocation works, an installed skill's link to `foundation.md` resolves, and the composition corpus routes without damaging truncation or chronic sibling overlap. Stop release on omission or damaging host shortening; do not silently split the plugin.

## Context exceptions

There are no v1 context-budget or runtime-surface exceptions. Add one only with the failing eval, measured before/after context, why a smaller instruction or existing repository tool cannot close the gap, and a condition for removal.

## Deferred capabilities

Packaging/publication, frameworks, vendor databases, database operations, security review, incident management, release engineering, repository governance, general testing strategy, and code review remain separate. Add a new focused skill only after trigger and task evidence shows a recurring gap.
