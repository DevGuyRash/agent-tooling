---
name: skill-auditor
description: >-
  Perform structured, reproducible audits of agent skills — testing mechanical
  correctness, agent usability, output quality, context efficiency, EARS
  compliance, prompt complexity, multi-agent coordination, audit convergence
  (reproducibility across runs), finding divergence (specificity and
  tailoring), AGENTS.md adherence (rule absorption verification),
  documentation/runtime staleness drift detection, CLI discoverability
  helper coverage, idempotency, error recovery, and credential safety.
  Covers 25 audit domains (D1–D25) with confidence-scored findings at every
  level. Use when (1) auditing or health-checking a skill end-to-end, (2)
  verifying AGENTS.md adherence, audit convergence, or finding divergence,
  or (3) validating scripts, CLIs, context/token footprint, EARS requirement
  syntax, prompt complexity, name consistency, dispatch prompt quality, or
  structured confidence-scored audit reports.
---

# Skill Auditor

A structured, phased audit framework for evaluating agent skills across 25
domains (D1–D25). The agent performs the audit and writes the report; bundled
scripts only gather deterministic evidence that helps the audit.

---

## Guidance delivery

You SHALL run `<skills-file-root>/scripts/audit-skill <command>` for guidance.
This CLI provides just-in-time routing. IF the CLI is unavailable, read the
corresponding reference file instead.

| Command | What it provides | Fallback reference |
|---------|------------------|--------------------|
| `audit-skill phases` | List all phases | `references/audit-phases-core.md` |
| `audit-skill phase <N>` | Detailed phase instructions | `references/audit-phases-core.md` or `audit-phases-analysis.md` |
| `audit-skill domains` | List all 25 domains | `references/domains-core.md`, `domains-analysis.md`, `domains-new.md` |
| `audit-skill domain <ID>` | Full domain spec | Corresponding `references/domains-*.md` |
| `audit-skill activate <traits>` | Domains for skill traits | `references/domains-core.md` § Activation Rules |
| `audit-skill hints <ID>` | Actionable hints | Inline in domain specs |
| `audit-skill next-steps` | Ordered audit steps | This file § Getting started |
| `audit-skill step <N>` | Detailed guidance for one audit step | This file § Getting started |
| `audit-skill report-workflow` | Report-writing workflow and finding schema | This file § Report finalization |
| `audit-skill confidence` | Scoring rules | `references/confidence-scoring.md` |
| `audit-skill report-template` | Report structure | `references/report-template.md` |
| `audit-skill check <name> <dir>` | Gather deterministic evidence with one helper script | Direct script invocation |
| `audit-skill check-all <dir>` | Gather deterministic evidence with all helper scripts | Sequential script invocation |
| `audit-skill self-check` | Validate the auditor's helper-script layer | `check-all` on own directory |

---

## Workflow overview

Every audit follows five primary phases plus a deterministic duplication gate.
The phases are agent-led: scripts can accelerate evidence gathering, but the
agent decides what matters and writes the final report.

| Phase | Name                  | Budget | Focus                                     |
|-------|-----------------------|--------|-------------------------------------------|
| 1     | Environment & Build   | ~15%   | Dead scripts block everything else        |
| 2     | API Surface           | ~25%   | Name mismatches are the #1 agent failure  |
| 3     | Workflow Simulation   | ~30%   | The agent's actual experience             |
| 4     | Context & Token       | ~15%   | Quantifies what phases 1-3 found          |
| 4b    | Duplication Gate      | ~5%    | Deterministic duplicate/contradiction gate |
| 5     | Output Quality        | ~15%   | Depth, consistency, EARS, complexity      |

WHEN the skill orchestrates subagents, THEN add **Phase 3b: Multi-Agent
Audit** between phases 3 and 4. Read
`<skills-file-root>/references/multi-agent-audit.md` before starting Phase 3.

---

## Getting started

1. Identify the target skill directory and read its SKILL.md end-to-end.
2. Create a running report file immediately; add findings as you discover them.
3. Map the directory tree: scripts, references, binaries, configs.
4. Determine activated domains: run `<skills-file-root>/scripts/audit-skill activate <traits...>`.
5. List the workflow: run `<skills-file-root>/scripts/audit-skill next-steps`.
6. Drill into the current step: run `<skills-file-root>/scripts/audit-skill step <N>`.
7. Read phase instructions: run `<skills-file-root>/scripts/audit-skill phase 1`.
8. Create a fresh workspace in `/tmp/audit-workspace/`.
9. Run helper scripts when they add evidence quickly; when a script is missing or weak, perform the equivalent manual inspection and record that gap.
10. Proceed through each phase in order. Run `audit-skill phase <N>` for guidance.
11. Finalize the actual audit output using `<skills-file-root>/scripts/audit-skill report-workflow` and `<skills-file-root>/scripts/audit-skill report-template`.

Trait → domain activation lives in the router manifest and domain references.
Run `<skills-file-root>/scripts/audit-skill activate <traits...>` for the
current skill instead of relying on a duplicated quick-reference table.

---

## Confidence scoring

Every finding needs confidence: `HIGH [H]` for deterministic script output,
`MEDIUM [M]` for traced agent inspection, and `LOW [L]` for weaker pattern
matching. Run `<skills-file-root>/scripts/audit-skill confidence` for details.

---

## Severity framework

Use `BLOCKER` for no-workaround workflow failure, `MAJOR` for wrong output or
serious waste, `MINOR` for workaround-required friction, and `NIT` for polish.

---

## Error recovery

WHEN a phase fails mid-audit, you SHALL:
- Record all findings discovered so far — partial findings are usable.
- WHEN a deterministic script fails, re-run it individually with
  `<skills-file-root>/scripts/audit-skill check <name> <dir>` for details.
- You MAY restart the failed phase from its beginning. You SHALL NOT restart
  completed phases unless new information invalidates earlier findings.
- WHEN `check-all` reports failures, proceed with remaining phases and note
  the failure in the report.

---

## Report finalization

WHEN all phases are complete:

1. Read the report workflow: `<skills-file-root>/scripts/audit-skill report-workflow`.
2. Read the report template: `<skills-file-root>/scripts/audit-skill report-template`.
3. Fill in each phase section from accumulated findings as an agent judgment, not as a raw script dump.
4. Use helper-script output as evidence and confidence support, but do not treat `check-all` or `self-check` as the audit itself.
5. Write the executive summary LAST.
6. Assign the final verdict: **SHIP** | **SHIP WITH FIXES** | **DO NOT SHIP**.
7. Include aggregate confidence score and distribution.
8. Verify D18 convergence, D19 divergence, D20 adherence, D21 staleness,
   and D22 discoverability per the domain specs.
9. Use the severity framework consistently: **BLOCKER** | **MAJOR** | **MINOR** | **NIT**.

### What `self-check` means

`audit-skill self-check` validates only the deterministic helper layer. A real
self-audit still requires the agent to walk phases, synthesize findings, and
write the report.

---

## Reference index

Load only the reference needed for the current phase:
- `references/audit-phases-core.md` for phases 1–3
- `references/audit-phases-analysis.md` for phases 4–5
- `references/domains-core.md`, `references/domains-analysis.md`, and `references/domains-new.md` for domain specs
- `references/multi-agent-audit.md` only when the skill dispatches subagents
- `references/confidence-scoring.md` and `references/report-template.md` during report synthesis
- `references/cli-implementation-guide.md` when auditing another skill's router CLI
