# Campaign: Replace With Name

> **Not executable.** A campaign parent is never run, never rendered to a `/goal`,
> and has no contract hash. Compile **at most one ready child** into
> `.goals/current.md`, validate, and lock it before running Codex `/goal`. If no
> child is ready, stop here and report what blocks the most promising child.

## Intent

[Parent aspiration.]

## Completeness Dimensions

- [dimension]

## Goal Graph

### G-001: First launchable child

- Status: ready
- Depends on: none
- Blocks: [ids]
- Terminal state:
- Verifier:

### G-002: Blocked child

- Status: blocked
- Depends on: G-001
- Missing decision:

### G-003: Not-launchable child

- Status: not-launchable
- Reason: [no checkable terminal state / no verifier / unbounded scope]
- Needed to launch: [the missing spine field or decision]

## Selection Recommendation

Compile at most one ready child. Run G-001 first because [reason]. If no child is
ready, stop here and report what blocks the most promising child.
