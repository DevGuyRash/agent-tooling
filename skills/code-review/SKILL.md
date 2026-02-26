---
name: code-review
description: Multi-agent code review/apply orchestration via `mpcr` protocols.
compatibility: Cross-platform. On POSIX, `<skills-file-root>/scripts/mpcr` runs directly. On Windows, `<skills-file-root>/scripts/mpcr.cmd` tries `bash` then falls back to `<skills-file-root>/scripts/mpcr.ps1` (PowerShell 5.1+). If the binary is not prebuilt, requires a Rust toolchain to build `<skills-file-root>/scripts/mpcr-src`.
---

# Code Review

## Path Resolution
All relative paths in this skill resolve from `<skills-file-root>` — the directory containing this `SKILL.md` file.
- **mpcr binary:** `<skills-file-root>/scripts/mpcr` (POSIX) or `<skills-file-root>/scripts/mpcr.cmd` (Windows)
- **Protocol references:** `<skills-file-root>/references/`
- **Source:** `<skills-file-root>/scripts/mpcr-src/`

## Role Detection
IF prompt contains `MPCR_DISPATCH_ROLE=`, `MPCR_APPLICATOR_ROLE=`, or `## Proof Packet:` THEN you are a WORKER.
- STOP reading this file.
- Follow only the dispatch prompt.
- You MAY run `mpcr protocol *` for phase guidance.

Otherwise you are ORCHESTRATOR.

## Orchestrator Bootstrap
1. Run `mpcr protocol orchestrator`
2. Run `mpcr protocol domains`
3. WHEN full-cycle, run `mpcr protocol fullcycle`

All workflow detail (dispatch, quality gates, domain discovery, cleanup) lives in protocol output.

## Platform Resilience
- WHEN the runtime returns `agent thread limit reached`, reduce batch size by half, close idle explorers, and retry.
- WHEN a subagent returns null or empty completion, treat as failed; re-dispatch once. IF retry also returns null, record as Residual Risk and close the child with `--set-status CANCELLED`.

## Universal Rules
- Do not paste raw diffs unless requested.
- Code excerpts: <= 12 lines each, <= 3 total.
- Scratch artifacts under `.local/tmp/` only; delete when done.
- Refresh guidance at phase transitions with `mpcr protocol`.

## Fallback
IF protocol CLI is unavailable, read:
- `<skills-file-root>/references/reviewer-protocol.md`
- `<skills-file-root>/references/applicator-protocol.md`
