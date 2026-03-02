---
name: skill-auditor
description: >-
  Perform structured, reproducible audits of agent skills — testing mechanical
  correctness, agent usability, output quality, context efficiency, EARS
  compliance, prompt complexity, multi-agent coordination, audit convergence
  (reproducibility across runs), finding divergence (specificity and
  tailoring), AGENTS.md adherence (rule absorption verification), and
  documentation/runtime staleness drift detection, and CLI discoverability
  helper coverage. Covers 22 audit domains (D1–D22) with confidence-scored
  findings at every level.
  Use when (1) auditing or health-checking a skill end-to-end, (2) verifying
  AGENTS.md adherence, audit convergence, or finding divergence, or (3)
  validating scripts, CLIs, context/token footprint, EARS requirement syntax,
  prompt complexity, name consistency, dispatch prompt quality, or structured
  confidence-scored audit reports.
---

# Skill Auditor

A structured, phased audit framework for evaluating agent skills. The auditor
checks every way a skill can fail, confuse, or waste tokens for an agent —
then produces a clear, actionable report with confidence-scored findings.

---

## Workflow overview

Every audit follows five primary phases plus a deterministic duplication gate.
You SHALL work through them in order WHEN later phases depend on earlier
findings.

| Phase | Name                  | Budget | Focus                                     |
|-------|-----------------------|--------|-------------------------------------------|
| 1     | Environment & Build   | ~15%   | Dead scripts block everything else        |
| 2     | API Surface           | ~25%   | Name mismatches are the #1 agent failure  |
| 3     | Workflow Simulation   | ~30%   | The agent's actual experience             |
| 4     | Context & Token       | ~15%   | Quantifies what phases 1-3 found          |
| 4b    | Duplication Gate      | ~5%    | Deterministic duplicate/contradiction gate |
| 5     | Output Quality        | ~15%   | Depth, consistency, EARS, complexity      |

WHEN the skill orchestrates subagents (dispatches workers, uses multi-agent
patterns), THEN you SHALL add **Phase 3b: Multi-Agent Audit** between phases
3 and 4.

---

## Audit domains

Each audit activates a subset of 22 domains (D1–D22) based on the skill's
characteristics. Domains map AGENTS.md rules to concrete checks with scripts
and severity mappings.

You SHALL read `<skills-file-root>/references/domains.md` and load only the
domains activated for the current audit.

### Domain activation (quick reference)

| Skill characteristic            | Domains to activate           |
|---------------------------------|-------------------------------|
| Universal (always)              | D1, D2, D3, D4, D6, D8, D18, D20, D21 |
| Has `scripts/`                  | + D12                         |
| Has `references/`               | + D16, D17                    |
| Dispatches subagents            | + D9                          |
| CLI-heavy                       | + D5, D7, D10, D11, D22       |
| Instruction-heavy               | + D14, D15                    |
| Cross-skill deps                | + D13                         |
| Produces variant outputs        | + D19                         |
| References external rules       | + D20 (already universal)     |

---

## Getting started

You SHALL follow these steps in order:

1. You SHALL identify the target skill from the user's request or prompt
   context. Locate its `SKILL.md` and map the directory tree.

2. You SHALL read the target skill's SKILL.md end-to-end to build a mental
   model. You SHALL NOT execute anything during this step.

3. You SHALL determine which domains to activate using the activation table
   above and the full rules in `<skills-file-root>/references/domains.md`.

4. You SHALL read the appropriate phase reference before starting:
   - `<skills-file-root>/references/audit-phases-core.md` — Phases 1–3
   - `<skills-file-root>/references/audit-phases-analysis.md` — Phases 4–5

5. You SHALL create a fresh workspace in a writable directory (e.g.,
   `/tmp/audit-workspace/`). You SHALL NOT modify the target skill's
   directory.

6. You SHALL start Phase 1 and proceed through each phase in order.

7. You SHALL write findings to a running report file as you discover them.
   You SHALL NOT defer finding documentation until report finalization.

8. WHEN all phases are complete THEN you SHALL finalize the report using
   `<skills-file-root>/references/report-template.md`.

---

## Confidence scoring

Every finding gets a confidence level alongside its severity. This separates
script-verified facts from agent-inferred patterns.

| Level  | Tag   | Source                          |
|--------|-------|---------------------------------|
| HIGH   | `[H]` | Deterministic script output     |
| MEDIUM | `[M]` | Agent inspection with evidence  |
| LOW    | `[L]` | Pattern matching without trace  |

You SHALL read `<skills-file-root>/references/confidence-scoring.md` for the
full assignment rules, gated verdicts, and aggregate scoring formula.

You SHALL assign a confidence level to EVERY finding as you discover it.
You SHALL NOT defer confidence assignment to report finalization. WHEN a
finding originates from script output, THEN confidence SHALL be HIGH. WHEN
a finding originates from agent inspection with traced evidence, THEN
confidence SHALL be MEDIUM. WHEN a finding originates from pattern matching
without a full trace, THEN confidence SHALL be LOW.

---

## Severity framework

| Severity    | Definition                                         | Agent impact                          |
|-------------|----------------------------------------------------|---------------------------------------|
| **BLOCKER** | Workflow cannot proceed. No workaround.             | Agent fails or enters error loop.     |
| **MAJOR**   | Workflow proceeds with wasted tokens or wrong output.| Degraded quality or efficiency.       |
| **MINOR**   | Suboptimal but agent can work around it.            | Longer path to success.               |
| **NIT**     | Style, naming, or documentation polish.             | No functional impact.                 |

A finding's severity SHALL reflect the worst realistic outcome for an agent
encountering it, not the theoretical worst case.

---

## Deciding what to audit

| Skill type                     | Emphasize          | De-emphasize              |
|--------------------------------|--------------------|---------------------------|
| CLI-heavy (scripts/binaries)   | Phase 1, Phase 2   | Phase 5 (if no templates) |
| Multi-agent orchestrator       | Phase 3, Phase 3b  | Phase 1 (if no build)     |
| Document generator             | Phase 3, Phase 5   | Phase 2 (if no CLI)       |
| Reference-heavy (guidelines)   | Phase 4, Phase 5   | Phase 1, Phase 2          |
| Workflow skill (gitops, CI/CD) | Phase 1, Phase 3   | Phase 5                   |

---

## Multi-agent detection

A skill needs Phase 3b WHEN any of these are true:

- It mentions "subagent", "worker", "dispatch", or "orchestrator"
- It has dispatch templates, role definitions, or worker prompts
- It spawns parallel agents for different domains or file clusters
- It has an "orchestrator" mode distinct from "worker" mode
- Its SKILL.md describes a concurrency cap or agent count

WHEN detected, you SHALL read
`<skills-file-root>/references/multi-agent-audit.md` before starting Phase 3.

---

## Test project creation

Phase 3 requires a test project appropriate to the skill's domain:

- **Minimal but non-trivial** — enough to exercise core functionality.
- **Deliberately flawed** — include 3–5 known issues the skill should find.
- **Self-contained** — no external dependencies beyond what the skill expects.
- **Version-controlled** — initialize git for diff-based skills.

| Skill domain       | Test project suggestion                              |
|--------------------|------------------------------------------------------|
| Code review        | Small app (100–200 LOC) with security/design issues  |
| Document generation| 2–3 page outline with mixed content types            |
| CI/CD / DevOps     | Minimal project needing build/test/deploy config     |
| Data processing    | Small CSV/JSON with edge cases                       |

---

## Running scripts

Helper scripts accelerate deterministic checks. These are optional — you can
perform equivalent checks manually.

| Script | Purpose | Phase |
|--------|---------|-------|
| `<skills-file-root>/scripts/surface_check.sh <skill-directory>` | CRLF, permissions, shebangs, structure | 1 |
| `<skills-file-root>/scripts/measure_context.sh <skill-directory> [--cli <bin>]` | Chars/tokens of docs and CLI outputs | 4 |
| `<skills-file-root>/scripts/frontmatter_check.sh <skill-directory>` | Frontmatter validity (D2) | 1 |
| `<skills-file-root>/scripts/description_check.sh <skill-directory>` | Description quality (D3) | 1 |
| `<skills-file-root>/scripts/path_token_check.sh <skill-directory>` | Path token usage (D4) | 1 |
| `<skills-file-root>/scripts/cold_start_check.sh <skill-directory>` | Cold-start timing (D11) | 1 |
| `<skills-file-root>/scripts/dependency_check.sh <skill-directory>` | Script dependencies (D12) | 1 |
| `<skills-file-root>/scripts/name_consistency_check.sh <skill-directory> --cli <bin>` | Name consistency (D5) | 2 |
| `<skills-file-root>/scripts/error_quality_check.sh <skill-directory> --cli <bin>` | Error message quality (D7) | 2 |
| `<skills-file-root>/scripts/output_size_check.sh <skill-directory> --cli <bin>` | Output size discipline (D10) | 2 |
| `<skills-file-root>/scripts/staleness_check.sh <skill-directory> [--cli <bin>] [--format text|json]` | Documentation/runtime staleness drift (D21) | 2 |
| `<skills-file-root>/scripts/discoverability_check.sh <skill-directory> [--cli <bin>] [--format text|json]` | CLI discoverability helper coverage (D22) | 2 |
| `<skills-file-root>/scripts/ears_check.sh <skill-directory>` | EARS compliance (D14) | 5 |
| `<skills-file-root>/scripts/prompt_complexity_check.sh <skill-directory>` | Prompt complexity (D15) | 5 |
| `<skills-file-root>/scripts/duplication_check.sh <skill-directory> [--scope operative|advisory|all] [--format text|json] [--max-hops N]` | Deterministic duplication detection and gate (D16) | 4b |
| `<skills-file-root>/scripts/reference_depth_check.sh <skill-directory>` | Reference depth (D17) | 4 |

---

## Report finalization

WHEN all phases are complete THEN you SHALL compile the final report:

1. You SHALL read `<skills-file-root>/references/report-template.md`.
2. You SHALL fill in each section from accumulated findings.
3. You SHALL write the executive summary LAST — it synthesizes, not introduces.
4. You SHALL assign the final verdict:
   - **SHIP**: Zero BLOCKERs, zero MAJORs.
   - **SHIP WITH FIXES**: Zero BLOCKERs, 1–3 MAJORs with clear fixes.
   - **DO NOT SHIP**: Any BLOCKERs, or MAJORs requiring design rethink.
5. You SHALL include the aggregate confidence score and distribution.
6. You SHALL verify D18 (convergence): WHEN any script produces different
   output on a second run against the same unchanged target, THEN you SHALL
   flag the variance as a D18 finding.
7. You SHALL treat D16 as a deterministic gate: operative duplication
   findings MAY block shipment, advisory-only duplication findings SHALL NOT.
8. You SHALL verify D19 (divergence): WHEN >40% of findings lack
   skill-specific file:line anchors, THEN you SHALL flag insufficient
   divergence as a D19 finding.
9. You SHALL verify D20 (adherence): WHEN any AGENTS.md rule lacks a
   corresponding audit domain or check, THEN you SHALL flag the gap as a
   D20 finding.
10. You SHALL verify D21 (staleness drift): WHEN documented commands or
    examples no longer match current runtime behavior, THEN you SHALL flag
    the mismatch as a D21 finding with script evidence where available.
11. You SHALL verify D22 (CLI discoverability): WHEN enum-like CLI parameters
    are documented but no one-step discovery helper exists (`--help`, `--list`,
    or equivalent), THEN you SHALL flag a D22 finding.

---

## Reference index

You SHALL load only the reference needed for the current phase.

| File | When to read |
|------|-------------|
| `<skills-file-root>/references/audit-phases-core.md` | Before Phase 1 — Phases 1–3 details |
| `<skills-file-root>/references/audit-phases-analysis.md` | Before Phase 4 — Phases 4–5 details |
| `<skills-file-root>/references/domains.md` | During domain activation — load activated domains only |
| `<skills-file-root>/references/confidence-scoring.md` | During report finalization |
| `<skills-file-root>/references/multi-agent-audit.md` | Before Phase 3 when skill orchestrates subagents |
| `<skills-file-root>/references/report-template.md` | During report finalization |
