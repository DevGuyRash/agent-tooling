# Audit Report Template

Copy this template and fill it in. Write the executive summary LAST after
all findings are compiled. Replace all `<placeholder>` text.

## Table of contents

- [Executive Summary](#executive-summary)
- [Phase 1: Environment & Build](#1-environment--build-phase-1)
- [Phase 2: API Surface](#2-api-surface-phase-2)
- [Phase 3: Workflow Simulation](#3-workflow-simulation-phase-3)
- [Phase 3b: Multi-Agent Audit](#3b-multi-agent-audit-phase-3b)
- [Phase 4: Context & Token](#4-context--token-analysis-phase-4)
- [Phase 4b: Duplication Gate](#4b-duplication-gate-phase-4b)
- [Phase 5: Output Quality](#5-output-quality-phase-5)
- [EARS Compliance](#6-ears-compliance-analysis)
- [Prompt Complexity](#7-prompt-complexity-analysis)
- [Convergence (D18)](#8-convergence-analysis-d18)
- [Divergence (D19)](#9-divergence-analysis-d19)
- [Adherence (D20)](#10-adherence-analysis-d20)
- [Staleness (D21)](#11-staleness-analysis-d21)
- [CLI Discoverability (D22)](#12-cli-discoverability-d22)
- [Improvement Recommendations](#improvement-recommendations)
- [Confidence Summary](#confidence-summary)

---

```markdown
# Skill Audit Report: <skill-name>

**Date:** <YYYY-MM-DD>
**Skill path:** <path/to/skill>
**Verdict:** SHIP | SHIP WITH FIXES | DO NOT SHIP

---

## Executive Summary

<2-4 sentences: what was audited, what the overall quality is, what the
critical issues are, and the final verdict. Write this LAST.>

**Finding counts:** <N> BLOCKER, <N> MAJOR, <N> MINOR, <N> NIT
**Confidence distribution:** H:<N> · M:<N> · L:<N>
**Aggregate confidence score:** <N>% (<high-confidence | mixed-confidence | low-confidence>)

### Domains Activated

| Domain | Script Run | Findings |
|--------|-----------|----------|
| D1 file-hygiene | ✅/❌/N/A | <count> |
| D2 frontmatter-validity | ✅/❌/N/A | <count> |
| D3 description-quality | ✅/❌/N/A | <count> |
| D4 path-token-usage | ✅/❌/N/A | <count> |
| D5 name-consistency | ✅/❌/N/A | <count> |
| D6 command-isolation | ✅/❌/N/A | <count> |
| D7 error-message-quality | ✅/❌/N/A | <count> |
| D8 progressive-disclosure | ✅/❌/N/A | <count> |
| D9 dispatch-prompt-quality | ✅/❌/N/A | <count> |
| D10 output-size-discipline | ✅/❌/N/A | <count> |
| D11 cold-start-readiness | ✅/❌/N/A | <count> |
| D12 script-self-containment | ✅/❌/N/A | <count> |
| D13 cross-skill-integration | ✅/❌/N/A | <count> |
| D14 ears-compliance | ✅/❌/N/A | <count> |
| D15 prompt-complexity | ✅/❌/N/A | <count> |
| D16 duplication-detection | ✅/❌/N/A | <count> |
| D17 reference-depth | ✅/❌/N/A | <count> |
| D18 convergence | ✅/❌/N/A | <count> |
| D19 divergence | ✅/❌/N/A | <count> |
| D20 adherence | ✅/❌/N/A | <count> |
| D21 staleness-drift | ✅/❌/N/A | <count> |
| D22 CLI Discoverability | ✅/❌/N/A | <count> |

---

## 1. Environment & Build (Phase 1)

### Script/Binary Execution Results

| Item | Status | Error | Severity | Fix |
|------|--------|-------|----------|-----|
| <script/binary> | ✅/❌ | <error if failed> | <severity> | <fix> |

### Build Assessment

- **Pre-built binary available:** Yes / No
- **Build time from scratch:** <time>
- **Dependencies required:** <list>
- **Build succeeds:** Yes / No

### Phase 1 Findings

#### <ID>: <Title>

- **Severity:** BLOCKER | MAJOR | MINOR | NIT
- **Confidence:** HIGH [H] | MEDIUM [M] | LOW [L] — <evidence basis>
- **Anchor:** <file:line or command>
- **Evidence:** <exact error, output, or measurement>
- **Impact:** <what happens to an agent>
- **Fix:** <specific recommendation>

---

## 2. API Surface (Phase 2)

### CLI Surface Tree

```
<tool>
├── <subcommand> [flags]
│   ├── <sub-sub>
│   └── <sub-sub>
└── <subcommand> [flags]
```

### Name Consistency

| Documented Name | CLI Representation | Documented? | Works? |
|----------------|-------------------|-------------|--------|
| <name> | <cli-value> | ✅/❌ | ✅/❌ |

### Error Quality Assessment

<Brief summary: are errors short and actionable, or noisy and wasteful?>

### Phase 2 Findings

<Findings using the standard format with Confidence line>

---

## 3. Workflow Simulation (Phase 3)

### Test Project

- **Type:** <language/domain>
- **Size:** <LOC or file count>
- **Deliberate issues:** <list of planted issues>

### Step-by-Step Walkthrough

| Step | Command/Action | Status | Output Size | Clarity | Notes |
|------|---------------|--------|-------------|---------|-------|
| 1 | <command> | ✅/❌ | <lines/chars> | 1/2/3 | <notes> |

### Ambiguity Score

- Clear (1): <N> steps
- Inferrable (2): <N> steps
- Ambiguous (3): <N> steps
- **Overall clarity:** <assessment>

### Phase 3 Findings

<Findings using the standard format with Confidence line>

---

## 3b. Multi-Agent Audit (Phase 3b)

<Include this section only when the skill orchestrates subagents.>

### Dispatch Role Inventory

| Role | Prompt Size | Domain-Specific % | Depth vs. Median |
|------|-----------|-------------------|--------------------|
| <role> | <chars> | <N%> | <N%> |

### Cross-Role Consistency

| Section | <role1> | <role2> | <role3> | ... |
|---------|---------|---------|---------|-----|
| <section> | ✅/❌ | ✅/❌ | ✅/❌ | ... |

### Context Footprint

- **Orchestrator context:** <N> tokens
- **Per-worker context:** <N> tokens
- **Total for N workers:** <N> tokens

### Phase 3b Findings

<Findings using the standard format with Confidence line>

---

## 4. Context & Token Analysis (Phase 4)

### Context Budget

| Component | Chars | Est. Tokens | Loaded When |
|-----------|-------|-------------|-------------|
| <component> | <N> | <N> | <when> |
| **TOTAL** | **<N>** | **<N>** | |

### Duplication Map

| Content | Appears In | Wasted Tokens |
|---------|-----------|---------------|
| <duplicated content> | <doc1, doc2, ...> | <N> |
| **TOTAL WASTE** | | **<N>** |

### Reduction Recommendations

| Cut | Tokens Saved | Risk |
|-----|-------------|------|
| <specific cut> | <N> | <low/medium/high> |
| **TOTAL SAVINGS** | **<N>** | |

### Phase 4 Findings

<Findings using the standard format with Confidence line>

---

## 4b. Duplication Gate (Phase 4b)

**Gate status:** PASS | PASS WITH MINORS | FAIL
**Highest operative severity:** NONE | MINOR | MAJOR | BLOCKER
**Operative duplicate waste:** <N> tokens
**Advisory duplicate waste:** <N> tokens

### Operative Exact Directive Duplicates

| Severity | Confidence | Text | Files | Waste |
|----------|------------|------|-------|-------|
| BLOCKER/MAJOR/MINOR | HIGH [H] | <normalized directive> | <doc1, doc2, ...> | <N> |

### Operative Exact Block Duplicates

| Severity | Confidence | Preview | Files | Waste |
|----------|------------|---------|-------|-------|
| MAJOR/MINOR | HIGH [H] | <normalized block preview> | <doc1, doc2, ...> | <N> |

### Operative Contradiction Candidates

| Severity | Confidence | Key | Positive | Negative | Files |
|----------|------------|-----|----------|----------|-------|
| BLOCKER | HIGH [H] | <normalized key> | <example> | <example> | <doc1, doc2, ...> |

### Advisory Duplication Findings

| Severity | Confidence | Category | Summary | Files |
|----------|------------|----------|---------|-------|
| NIT | HIGH [H] | directive/block/contradiction | <short summary> | <doc1, doc2, ...> |

### Phase 4b Findings

<Findings using the standard format with Confidence line>

---

## 5. Output Quality (Phase 5)

### Variant Comparison

| Variant | Lines | Chars | vs. Median | Tailoring |
|---------|-------|-------|-----------|-----------|
| <variant> | <N> | <N> | <N%> | <low/medium/high> |

### Anti-Laziness Guardrails

| Guardrail | Present? | Effective? |
|-----------|----------|-----------|
| Minimum counts | ✅/❌ | <assessment> |
| Specificity requirements | ✅/❌ | <assessment> |
| Anti-pattern examples | ✅/❌ | <assessment> |

### Phase 5 Findings

<Findings using the standard format with Confidence line>

---

## 6. EARS Compliance Analysis

**EARS Coverage:** <N>% of directive lines use EARS keywords
**Rating:** HIGH (>70%) | MODERATE (40-70%) | LOW (<40%)

### Per-File Breakdown

| File | Directive Lines | Conditional Lines | Bare Imperatives | Vague | Coverage |
|------|----------------|-------------------|------------------|-------|----------|
| <file> | <N> | <N> | <N> | <N> | <N>% |

### Top Ambiguity Risks

| # | Location | Current Text | Suggested EARS Rewrite | Severity |
|---|----------|-------------|----------------------|----------|
| 1 | <file:line> | "<current>" | "<rewrite>" | MAJOR/MINOR |

### EARS Findings

<Findings using the standard format with Confidence line>

---

## 7. Prompt Complexity Analysis

**Aggregate Score:** <N>/100 (<LOW | MODERATE | HIGH>)

### Per-File Metrics

| File | Cond Density | Nest Depth | Neg Density | Xrefs | Vars | Score |
|------|-------------|-----------|-------------|-------|------|-------|
| <file> | <N>/para | <N> | <N>% | <N> | <N> | <N>/100 |

### Hotspots

| Location | Dimension | Value | Rating |
|----------|-----------|-------|--------|
| <file:lines> | <dimension> | <value> | MAJOR/MINOR |

### Complexity Findings

<Findings using the standard format with Confidence line>

---

## 8. Convergence Analysis (D18)

**Script Idempotency:** <N>/<N> scripts produce identical output on repeated runs
**Finding Consistency:** <assessment of whether findings would reproduce>

### Convergence Checks

| Check | Result | Confidence |
|-------|--------|------------|
| Script output idempotency | ✅/❌ | HIGH [H] |
| Rubric clarity (would two agents agree?) | <assessment> | MEDIUM [M] |
| Threshold definitions (are thresholds numeric?) | ✅/❌ | HIGH [H] |

### Convergence Findings

<Findings using the standard format with Confidence line>

---

## 9. Divergence Analysis (D19)

**Finding Specificity:** <N>% of findings have file:line anchors
**Recommendation Tailoring:** <assessment — generic vs. skill-specific>

### Divergence Checks

| Check | Result | Confidence |
|-------|--------|------------|
| Findings reference specific locations | <N>/<N> with anchors | HIGH [H] |
| Recommendations are actionable for this skill | <assessment> | MEDIUM [M] |
| No verbatim duplication across different audit targets | ✅/❌/N/A | MEDIUM [M] |

### Divergence Findings

<Findings using the standard format with Confidence line>

---

## 10. Adherence Analysis (D20)

**AGENTS.md Coverage:** <N>/<N> rules have corresponding audit checks
**Self-Compliance:** <assessment — does the auditor pass its own checks?>

### AGENTS.md Rule Coverage

| AGENTS.md Section | Audit Domain(s) | Covered? | Confidence |
|--------------------|-----------------|----------|------------|
| Command isolation | D6 | ✅/❌ | HIGH [H] / MEDIUM [M] |
| `<skills-file-root>` usage | D4 | ✅/❌ | HIGH [H] |
| Frontmatter and naming | D2, D5 | ✅/❌ | HIGH [H] |
| Description quality | D3 | ✅/❌ | HIGH [H] |
| File hygiene | D1 | ✅/❌ | HIGH [H] |
| Name consistency | D5 | ✅/❌ | MEDIUM [M] |
| Error message design | D7 | ✅/❌ | MEDIUM [M] |
| Progressive disclosure | D8 | ✅/❌ | MEDIUM [M] |
| Dispatch prompt design | D9 | ✅/❌ | MEDIUM [M] |
| Output size discipline | D10 | ✅/❌ | MEDIUM [M] |
| Cold-start readiness | D11 | ✅/❌ | HIGH [H] |
| Script self-containment | D12 | ✅/❌ | MEDIUM [M] |
| Integration testing | D13 | ✅/❌ | MEDIUM [M] |
| EARS compliance | D14 | ✅/❌ | HIGH [H] |
| Prompt complexity | D15 | ✅/❌ | HIGH [H] |
| Duplication detection | D16 | ✅/❌ | HIGH [H] |
| Reference depth | D17 | ✅/❌ | HIGH [H] |
| Convergence | D18 | ✅/❌ | MEDIUM [M] / HIGH [H] |
| Divergence | D19 | ✅/❌ | MEDIUM [M] / HIGH [H] |
| Adherence | D20 | ✅/❌ | MEDIUM [M] / HIGH [H] |
| Staleness drift | D21 | ✅/❌ | HIGH [H] / MEDIUM [M] |
| CLI discoverability helpers | D22 | ✅/❌ | HIGH [H] / MEDIUM [M] |

### Adherence Findings

<Findings using the standard format with Confidence line>

---

## 11. Staleness Analysis (D21)

**Example Drift Coverage:** <N>/<N> safe documented examples validated
**Behavior Claim Match Rate:** <N>% of tested examples match surrounding prose claims

### Staleness Checks

| Check | Result | Confidence |
|-------|--------|------------|
| Safe documented examples execute successfully | <N>/<N> | HIGH [H] |
| Documented flags/subcommands still resolve | <N>/<N> | HIGH [H] |
| Example claims match runtime transcript | <assessment> | MEDIUM [M] |
| Placeholder/underspecified examples tracked | <N> | MEDIUM [M] |

### Staleness Findings

<Findings using the standard format with Confidence line>

---

## 12. CLI Discoverability (D22)

**Discoverability Coverage:** <N>/<N> enum-like options expose one-step helper paths
**CLI Helper Affordances:** <assessment — --help/--list or equivalent available?>

### Discoverability Checks

| Check | Result | Confidence |
|-------|--------|------------|
| Enum-like options have doc helper examples | <N>/<N> | HIGH [H] |
| CLI help/list affordances are present | ✅/❌/N/A | HIGH [H] |
| Documented options appear in help corpus | <N>/<N> | HIGH [H] |
| Helper wording is actionable | <assessment> | MEDIUM [M] |

### Discoverability Findings

<Findings using the standard format with Confidence line>

---

## Improvement Recommendations

### Quick Wins (< 1 hour)

1. <recommendation>
2. <recommendation>

### Medium Effort (1-4 hours)

1. <recommendation>
2. <recommendation>

### Structural Changes (> 4 hours)

1. <recommendation>
2. <recommendation>

---

## Confidence Summary

### Confidence by Phase

| Phase | HIGH | MEDIUM | LOW | Total |
|-------|------|--------|-----|-------|
| 1 — Environment & Build   | <N>  | <N>    | <N> | <N>   |
| 2 — API Surface            | <N>  | <N>    | <N> | <N>   |
| 3 — Workflow Simulation    | <N>  | <N>    | <N> | <N>   |
| 3b — Multi-Agent (if applicable) | <N> | <N> | <N> | <N> |
| 4 — Context & Token        | <N>  | <N>    | <N> | <N>   |
| 4b — Duplication Gate      | <N>  | <N>    | <N> | <N>   |
| 5 — Output Quality         | <N>  | <N>    | <N> | <N>   |
| D18 — Convergence          | <N>  | <N>    | <N> | <N>   |
| D19 — Divergence           | <N>  | <N>    | <N> | <N>   |
| D20 — Adherence            | <N>  | <N>    | <N> | <N>   |
| D21 — Staleness Drift      | <N>  | <N>    | <N> | <N>   |
| D22 — CLI Discoverability  | <N>  | <N>    | <N> | <N>   |
| **Total** | **<N>** | **<N>** | **<N>** | **<N>** |

**Aggregate Score:** <N>%
**Assessment:** <high-confidence | mixed-confidence | low-confidence>

---

## Appendices

### Appendix A: Complete Name Mapping

<Full table of every documented name to CLI representation>

### Appendix B: Domain Script Outputs

<Raw output from each domain script that was run>

### Appendix C: Test Environment

- **Platform:** <OS, version>
- **Tools:** <languages, versions installed>
- **Date:** <when the audit was performed>
```
