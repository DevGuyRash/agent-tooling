# ADR 0006: Separate essential instructions from conditional references

- Status: Accepted
- Recorded: 2026-08-15
- Scope: Skill instruction and reference layout across the repository

## Context

Skills need accessible guidance for different tasks without loading every mode's detail into every assignment. External sources also change at different rates: current host policy and a reproducible observation need different kinds of links.

## Decision

Keep the task's essential purpose and constraints in the skill entry. Put substantial conditional detail in focused references when that improves use; a short self-contained skill can remain one document. Maintain guidance and its navigation with one owner, and supply required resources at the declared installation boundary.

Use rolling sources for deliberately current policy, immutable revisions for exact observations and reproducibility, and release-specific sources for a release-specific contract. Choose the reference layout and source horizon according to the recipient's actual need.

## Rationale and consequences

An unconditional preload adds irrelevant material; an over-reduced entry can hide a necessary constraint or make the executor search unnecessarily. Focused references allow detail to remain available while preserving a locally useful entry. File count and reference depth alone do not determine that result.

Package verification checks reference delivery and resolution. Claims about what a host loads or how loading affects model behavior need observations at that host. These responsibilities are maintained in [AGENTS.md](../../AGENTS.md); individual plugin loading experiments remain with their maintainer evidence.
