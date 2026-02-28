---
name: skill-auditor
description: >-
  Perform structured, reproducible audits of agent skills — testing mechanical
  correctness, agent usability, output quality, context efficiency, and
  multi-agent coordination. Use when auditing, evaluating, or health-checking
  a skill end-to-end — testing scripts and CLIs, measuring context/token
  footprint, checking name consistency, evaluating dispatch prompt quality,
  simulating agent workflows, or producing structured audit reports with
  severity-rated findings.
---

# Skill Auditor

A structured, phased audit framework for evaluating agent skills. The goal is
to find every way a skill can fail, confuse, or waste tokens for an agent —
then produce a clear, actionable report.

## Why this matters

Skills are force-multipliers: a well-built skill gets used thousands of times.
A bug in a skill doesn't just fail once — it fails every time an agent triggers
it. A name mismatch between docs and CLI wastes tokens on every invocation. A
20KB document that could be 5KB burns context budget across every session. The
audit catches these issues before they compound.

---

## Workflow overview

Every audit follows five phases, each with a clear scope and time budget. You
work through them in order because later phases depend on earlier findings.

| Phase | Name | Budget | Why it's first/here |
|-------|------|--------|-------------------|
| 1 | Environment & Build | ~15% | Dead scripts block everything else |
| 2 | API Surface Exhaustion | ~25% | Name mismatches are the #1 agent failure mode |
| 3 | Workflow Simulation | ~30% | The agent's actual experience is the ground truth |
| 4 | Context & Token Analysis | ~15% | Quantifies what phases 1-3 found qualitatively |
| 5 | Output Quality | ~15% | Checks depth, consistency, and tailoring |

If the skill orchestrates subagents (dispatches workers, uses multi-agent
patterns), add **Phase 3b: Multi-Agent Audit** between phases 3 and 4.

Read `<skills-file-root>/references/audit-phases.md` for the detailed
instructions for each phase. This document covers the overall approach,
severity framework, and report structure.

---

## Getting started

1. **Identify the skill to audit.** The user will point you to a skill
   directory or describe which skill to evaluate. Locate its `SKILL.md` and
   map the directory tree.

2. **Read the skill's SKILL.md end-to-end** to understand intent, triggers,
   workflows, and claimed deliverables. Don't execute anything yet — just
   build a mental model.

3. **Read the audit phase instructions:**
   ```
   <skills-file-root>/references/audit-phases.md
   ```

4. **Create a fresh workspace** (e.g., `/tmp/audit-workspace/` or any
   writable directory) for all test artifacts. Keep the skill's own
   directory untouched.

5. **Start Phase 1.** Execute, observe, document. Move through each phase.

6. **Accumulate findings** in a running report file in your workspace as
   you go. Don't wait until the end — write findings as you discover them.

7. **Finalize the report** using the template in
   `<skills-file-root>/references/report-template.md`.

---

## Severity framework

Use these consistently throughout the audit. The key distinction: severity is
about agent impact, not code quality in the abstract.

| Severity | Definition | Agent impact |
|----------|-----------|--------------|
| **BLOCKER** | Workflow cannot proceed. No workaround exists. | Agent fails, produces no output, or enters an error loop. |
| **MAJOR** | Workflow proceeds but agent wastes significant tokens, produces wrong output, or misses critical steps. | Agent completes but with degraded quality or efficiency. |
| **MINOR** | Suboptimal but agent can work around it without guidance. | Agent succeeds but takes a longer path. |
| **NIT** | Style, naming, or documentation polish. | No functional impact; affects maintainability. |

A finding's severity should reflect the *worst realistic outcome* for an agent
encountering it, not the theoretical worst case.

---

## Deciding what to audit

Not every phase applies equally to every skill. Use this to calibrate depth:

| Skill type | Emphasize | De-emphasize |
|-----------|-----------|-------------|
| CLI-heavy (has scripts/binaries) | Phase 1, Phase 2 | Phase 5 (if no templates) |
| Multi-agent orchestrator | Phase 3, Phase 3b | Phase 1 (if no build step) |
| Document generator (docx, pptx) | Phase 3, Phase 5 | Phase 2 (if no CLI) |
| Reference-heavy (guidelines, checklists) | Phase 4, Phase 5 | Phase 1, Phase 2 |
| Workflow skill (gitops, CI/CD) | Phase 1, Phase 3 | Phase 5 |

Spend your time where the skill's complexity lives.

---

## Multi-agent detection

A skill needs the multi-agent audit extension (Phase 3b) when any of these
are true:

- It mentions "subagent", "worker", "dispatch", or "orchestrator"
- It has dispatch templates, role definitions, or worker prompts
- It spawns parallel agents for different domains or file clusters
- It has an "orchestrator" mode distinct from "worker" mode
- Its SKILL.md describes a concurrency cap or agent count

When detected, read `<skills-file-root>/references/multi-agent-audit.md`
before starting Phase 3.

---

## Test project creation

Phase 3 (Workflow Simulation) requires a test project appropriate to the
skill's domain. The test project should be:

- **Minimal but non-trivial.** Enough code/content to exercise the skill's
  core functionality, but not so large it becomes the audit's bottleneck.
- **Deliberately flawed.** Include 3-5 known issues the skill should find
  (if the skill is a reviewer/linter/checker).
- **Self-contained.** No external dependencies beyond what the skill expects.
- **Version-controlled.** Initialize git so diff-based skills have something
  to work with.

For common skill types:

| Skill domain | Test project suggestion |
|-------------|----------------------|
| Code review | Small app (100-200 LOC) with security, performance, and design issues |
| Document generation | 2-3 page outline with mixed content types |
| CI/CD / DevOps | Minimal project needing build, test, deploy config |
| Data processing | Small CSV/JSON with edge cases (missing fields, encoding issues) |
| Frontend / design | Simple component with styling and interaction |

---

## Running scripts

The skill includes helper scripts for common audit measurements. These are
optional accelerators — you can do everything manually if needed.

| Script | Purpose | When to use |
|--------|---------|-------------|
| `scripts/surface_check.sh <skill-dir>` | Check CRLF, permissions, shebangs, file structure | Phase 1 |
| `scripts/measure_context.sh <skill-dir> [--cli <binary>] [--cli-mode help|run]` | Measure chars/tokens of all docs and CLI outputs (default help-only probing for safety) | Phase 4 |

Both scripts are self-contained and produce structured output you can paste
directly into the audit report.

**Recommended safe invocation (CLI probing):**
```bash
<skills-file-root>/scripts/measure_context.sh <skill-dir> --cli <binary> --cli-mode help
```

---

## Report finalization

After completing all phases, compile the final report:

1. Read the report template:
   `<skills-file-root>/references/report-template.md`

2. Fill in each section from your accumulated findings.

3. Write the executive summary LAST — it should synthesize, not introduce.

4. Assign the final verdict:
   - **SHIP**: Zero BLOCKERs, zero MAJORs. All NITs and MINORs are
     documented.
   - **SHIP WITH FIXES**: Zero BLOCKERs, 1-3 MAJORs with clear fixes.
     List the required fixes.
   - **DO NOT SHIP**: Any BLOCKERs, or MAJORs requiring design rethink.
     List the blockers.

5. Save the final report to the project directory or workspace and
   present it to the user.

---

## Reference index

Load only what you need for the current phase.

| File | When to read |
|------|-------------|
| `references/audit-phases.md` | Before starting Phase 1 — contains all phase details |
| `references/multi-agent-audit.md` | Before Phase 3 when skill orchestrates subagents |
| `references/report-template.md` | During report finalization |

## Script index

| Script | Purpose |
|--------|---------|
| `scripts/surface_check.sh` | CRLF, permissions, shebang, structure checks |
| `scripts/measure_context.sh` | Character/token measurement for context analysis (supports `--cli <binary>` and safe `--cli-mode help|run`) |
