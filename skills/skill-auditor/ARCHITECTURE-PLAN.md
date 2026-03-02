# Skill Auditor v2 — Architecture Plan

**Author:** Generative Architect (not implementer)
**Date:** 2026-02-28
**Status:** PROPOSAL — requires implementation pass
**Scope:** Expand `skills/skill-auditor` to bake in nearly all of AGENTS.md as
auditable domains, add confidence scoring, add EARS compliance checking, add
prompt complexity analysis, and detect documentation/runtime staleness drift.

---

## Implementation Delta

This proposal was written before the current branch expanded the auditor past
the original D1-D17 scope. The implemented branch now includes D18-D22,
including `D21 staleness-drift` backed by `scripts/staleness_check.sh` and
`D22 cli-discoverability` backed by `scripts/discoverability_check.sh`. Where
this document refers to "all 17 domains" or a D1-D17 rollout, treat that as
historical scope and prefer the current repo files (`SKILL.md`,
`references/domains.md`, `references/confidence-scoring.md`,
`references/report-template.md`) as the source of truth.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis](#2-current-state-analysis)
3. [AGENTS.md → Domain Mapping](#3-agentsmd--domain-mapping)
4. [New Audit Domains](#4-new-audit-domains)
5. [Confidence Scoring Framework](#5-confidence-scoring-framework)
6. [EARS Compliance Check (New Domain)](#6-ears-compliance-check-new-domain)
7. [Prompt Complexity Analysis (New Domain)](#7-prompt-complexity-analysis-new-domain)
8. [Self-Compliance Analysis](#8-self-compliance-analysis)
9. [Implementation Plan](#9-implementation-plan)
10. [File Structure](#10-file-structure)
11. [Script Specifications](#11-script-specifications)
12. [Migration Notes](#12-migration-notes)

---

## 1. Executive Summary

The current skill-auditor has 5 phases covering environment/build, API surface,
workflow simulation, context/token analysis, and output quality. These phases
are effective but generic — they don't encode the specific, hard-won rules from
AGENTS.md that represent the most common skill failure modes.

This plan proposes:

1. **Domain-based audit expansion**: Convert every substantive AGENTS.md section
   into a named audit domain with seed checks, severity mappings, and
   deterministic validation scripts where possible.

2. **Confidence scoring**: Every finding gets a confidence score (HIGH/MEDIUM/LOW)
   based on whether it was verified deterministically (script), verified by
   inspection (agent traced the evidence), or inferred (pattern-matched without
   full trace).

3. **EARS compliance check**: A new domain that analyzes skill instructions for
   adherence to EARS (Easy Approach to Requirements Syntax) patterns, flagging
   ambiguous directives that would benefit from WHEN/IF/WHILE/UNTIL structure.

4. **Prompt complexity analysis**: A new domain that evaluates dispatch prompts
   and SKILL.md instructions for cognitive load, nesting depth, conditional
   density, and agent-parseability.

5. **Self-compliance**: The auditor skill itself is analyzed section-by-section
   against every AGENTS.md rule it will enforce, with findings and fixes.

---

## 2. Current State Analysis

### 2.1 Existing Skill Structure

```
skills/skill-auditor/
├── SKILL.md                         (router — 178 lines, ~4,500 tokens)
├── references/
│   ├── audit-phases.md              (detailed phase procedures — 285 lines)
│   ├── multi-agent-audit.md         (Phase 3b for multi-agent skills — 195 lines)
│   └── report-template.md           (fill-in report template — 130 lines)
└── scripts/
    ├── measure_context.sh           (context/token measurement — 230 lines)
    └── surface_check.sh             (CRLF, permissions, anatomy — 215 lines)
```

### 2.2 What the Current Auditor Covers Well

- CRLF detection (deterministic via `surface_check.sh`)
- Script permission/shebang checks (deterministic)
- SKILL.md anatomy (frontmatter presence, field existence)
- Context/token measurement (deterministic via `measure_context.sh`)
- Multi-agent prompt evaluation (manual but structured)
- Workflow simulation with ambiguity scoring
- Output quality with anti-laziness guardrail checks

### 2.3 What the Current Auditor Does NOT Cover

These are all AGENTS.md sections with no corresponding audit check:

| AGENTS.md Section | Gap |
|-|-|
| Command isolation | No check that skills avoid env-var-across-command patterns |
| `<skills-file-root>` usage | No check that internal paths use the token correctly |
| Frontmatter naming rules | `surface_check.sh` checks presence but not format validity |
| Description quality | No check for trigger-condition coverage or keyword density |
| Name consistency (docs↔CLI) | Phase 2 covers this manually but no deterministic check |
| Error message design | Phase 2 touches this but no structured rubric |
| Progressive disclosure | Phase 4 measures sizes but doesn't evaluate the 3-layer model |
| Subagent dispatch prompt design | Phase 3b covers this but loosely |
| Output size discipline | No check for unbounded CLI outputs |
| Cold-start readiness | No timed first-run test |
| Script self-containment | No dependency audit for scripts |
| Integration testing | No cross-skill integration check |
| EARS compliance | Not addressed at all |
| Prompt complexity | Not addressed at all |
| Confidence scoring | Findings have severity but no confidence dimension |

---

## 3. AGENTS.md → Domain Mapping

Each AGENTS.md section becomes a named audit domain. Domains are grouped into
tiers based on whether they can be checked deterministically (script), require
structured agent inspection, or need simulation.

### 3.1 Domain Table

| # | Domain Slug | Source AGENTS.md Section | Tier | Script Support |
|---|---|---|---|---|
| D1 | `file-hygiene` | File hygiene (CRLF, permissions, shebangs) | Deterministic | `surface_check.sh` (existing) |
| D2 | `frontmatter-validity` | Frontmatter and naming | Deterministic | `frontmatter_check.sh` (new) |
| D3 | `description-quality` | Frontmatter — description field | Heuristic+Agent | `description_check.sh` (new) |
| D4 | `path-token-usage` | `<skills-file-root>` convention | Deterministic | `path_token_check.sh` (new) |
| D5 | `name-consistency` | Name consistency between docs and CLI | Agent+Script | `name_consistency_check.sh` (new) |
| D6 | `command-isolation` | Command isolation / env-var persistence | Agent | — (pattern search only) |
| D7 | `error-message-quality` | Error messages designed for agents | Agent+Script | `error_quality_check.sh` (new) |
| D8 | `progressive-disclosure` | Progressive disclosure and context budgets | Agent+Script | `measure_context.sh` (existing, extended) |
| D9 | `dispatch-prompt-quality` | Subagent dispatch prompt design | Agent | — |
| D10 | `output-size-discipline` | Output size discipline | Deterministic | `output_size_check.sh` (new) |
| D11 | `cold-start-readiness` | Cold-start readiness | Deterministic | `cold_start_check.sh` (new) |
| D12 | `script-self-containment` | Script self-containment | Agent+Script | `dependency_check.sh` (new) |
| D13 | `cross-skill-integration` | Integration testing across skills | Agent | — |
| D14 | `ears-compliance` | NEW — EARS requirement syntax | Agent+Script | `ears_check.sh` (new) |
| D15 | `prompt-complexity` | NEW — Prompt cognitive load | Agent+Script | `prompt_complexity_check.sh` (new) |
| D16 | `duplication-detection` | Each fact lives in exactly one place | Agent+Script | `duplication_check.sh` (new) |
| D17 | `reference-depth` | Reference file sizing and nesting | Deterministic | `reference_depth_check.sh` (new) |

### 3.2 Domain Activation Rules

You SHALL NOT run all 17 domains on every audit. Domain activation depends on
skill characteristics:

| Skill Characteristic | Always Active | Conditionally Active |
|---|---|---|
| Has scripts/ | D1, D2, D3, D4, D8, D12 | D5, D7, D10, D11 (if CLI) |
| Has references/ | D1, D2, D3, D4, D8, D16, D17 | D14, D15 |
| Dispatches subagents | D1, D2, D3, D4, D8, D9 | D14, D15 |
| CLI-heavy | D1, D2, D3, D4, D5, D7, D8, D10, D11 | D6 |
| Reference-only | D1, D2, D3, D4, D8, D14, D16, D17 | D15 |
| Cross-skill dependencies | D13 | — |

Universal domains (always run): D1, D2, D3, D4, D8.

---

## 4. New Audit Domains

### 4.1 D2: `frontmatter-validity`

**What it checks:** AGENTS.md rules for the `name` and `description` fields.

**Deterministic checks (script):**
- `name` matches parent directory name
- `name` is lowercase alphanumeric + hyphens only
- `name` ≤ 64 characters
- `name` does not start/end with `-` or contain `--`
- `description` exists and is ≤ 1024 characters

**Severity mapping:**
- Name/directory mismatch → BLOCKER (platforms use directory name for resolution)
- Name format violation → MAJOR (spec violation, may break platform indexing)
- Missing description → BLOCKER (skill will never trigger)
- Description over 1024 chars → MAJOR (spec violation)

**Script:** `frontmatter_check.sh <skill-dir>`

```
Output format:
  ✓ name "code-review" matches directory
  ✓ name format valid (lowercase, hyphens, 11 chars)
  ✗ description exceeds 1024 chars (1187 chars) [MAJOR]
  ✓ description contains trigger conditions ("Use when")
```

### 4.2 D3: `description-quality`

**What it checks:** Whether the description is effective for agent trigger
detection.

**Deterministic checks (script):**
- Contains "Use when" or equivalent trigger phrase
- Contains at least 3 distinct action verbs
- Contains at least 2 parenthesized trigger conditions (the `(1)...(2)...` pattern)
- Word count ≥ 30 (minimum viable description)

**Agent inspection checks:**
- Generate 5 prompts that SHOULD trigger this skill and 5 that SHOULD NOT
- Evaluate whether the description clearly distinguishes them
- Check for keyword coverage of realistic user phrasings

**Severity mapping:**
- No trigger conditions → MAJOR
- Fewer than 30 words → MAJOR
- Description is a single generic sentence → MAJOR
- Missing keyword variants → MINOR

**Script:** `description_check.sh <skill-dir>` (deterministic portion only)

### 4.3 D4: `path-token-usage`

**What it checks:** All internal file references use `<skills-file-root>` per
AGENTS.md convention.

**Deterministic checks (script):**
- Scan all `.md` files for hardcoded paths to files within the skill directory
- Verify that references to `scripts/`, `references/`, `assets/` use the token
- Flag any absolute paths or relative paths that don't use `<skills-file-root>`

**Exceptions:**
- Code blocks showing example output (not instructions to the agent)
- The frontmatter `compatibility` field (platform-specific)

**Severity mapping:**
- Hardcoded absolute path in instruction text → MAJOR (breaks portability)
- Bare relative path without token → MINOR (works but inconsistent)

**Script:** `path_token_check.sh <skill-dir>`

### 4.4 D5: `name-consistency`

**What it checks:** Every name in documentation resolves in the CLI, and every
CLI command is reachable from documentation.

**Deterministic checks (script — requires CLI binary):**
- Extract all `--role`, `--phase`, `--status`, `--mode` values from docs
- Extract all valid values from CLI `--help` output
- Cross-reference and report mismatches
- Check for mapping tables when human-friendly names differ from CLI slugs

**Agent inspection checks:**
- Walk every code example in SKILL.md and reference docs
- Execute each (substituting real IDs) and verify success
- Check that error messages include valid alternatives

**Severity mapping:**
- Documented name doesn't resolve in CLI → BLOCKER
- CLI value not mentioned in docs → MAJOR
- Human-friendly name without mapping table → MAJOR
- Inconsistent casing between docs and CLI → MINOR

**Script:** `name_consistency_check.sh <skill-dir> --cli <binary>`

### 4.5 D6: `command-isolation`

**What it checks:** Skill doesn't assume env vars persist across commands.

**Agent inspection checks:**
- Scan SKILL.md and references for patterns like:
  - `export VAR=...` followed by separate usage of `$VAR`
  - `cd <dir>` without being chained in the same command
  - Instructions to "set" a variable, then later "use" it
- Check if the skill recommends CLI flags over env vars
- Check wrapper scripts for `--use-env` patterns vs. explicit flags

**Severity mapping:**
- Instructions that require env-var persistence across agent commands → MAJOR
- Scripts using env vars that should use CLI flags → MINOR
- Documented `--use-env` pattern without CLI-flag alternative → MINOR

**Script:** None (too context-dependent for deterministic checking). However,
a grep-based heuristic could flag `export` followed by `$VAR` in separate
fenced code blocks.

### 4.6 D7: `error-message-quality`

**What it checks:** CLI/script errors are short, actionable, and
context-efficient per AGENTS.md rules.

**Deterministic checks (script — requires CLI binary):**
- Send deliberately bad input to every command
- Measure error output length (flag > 3 lines)
- Check for "valid values" in error messages
- Check for stack backtraces (RUST_BACKTRACE, Python tracebacks)
- Check for consistent `error:` / `hint:` format

**Severity mapping:**
- Stack backtrace on normal errors → MAJOR (token waste)
- Error > 10 lines → MAJOR
- Error doesn't include valid alternatives → MINOR
- Inconsistent error format → NIT

**Script:** `error_quality_check.sh <skill-dir> --cli <binary>`

### 4.7 D10: `output-size-discipline`

**What it checks:** CLI outputs are sized for agent context, not human terminals.

**Deterministic checks (script — requires CLI binary):**
- Run every documented command and measure output size
- Flag any output > 5,000 characters
- Check for `--summary-only`, `--max-items`, `--fields` filtering flags
- Check for separation of metadata from content

**Severity mapping:**
- Single command output > 10,000 chars with no compact mode → MAJOR
- Output > 5,000 chars with no filtering flags → MINOR
- Pretty-printed JSON as default (vs. compact) → MINOR
- No pagination for unbounded data → MINOR

**Script:** `output_size_check.sh <skill-dir> --cli <binary>`

### 4.8 D11: `cold-start-readiness`

**What it checks:** Skill is usable without installing toolchains or compiling.

**Deterministic checks (script):**
- Time the first execution of each script/binary
- Check if pre-built binaries exist for compiled tools
- Check `compatibility` frontmatter field for declared dependencies
- Verify vendored/self-contained scripts vs. install requirements

**Severity mapping:**
- First run requires > 60s build step with no pre-built binary → MAJOR
- First run requires `pip install` / `npm install` with no auto-install → MINOR
- No `compatibility` field when deps exist → MINOR
- Pre-built binary missing but source available → MINOR

**Script:** `cold_start_check.sh <skill-dir>`

### 4.9 D12: `script-self-containment`

**What it checks:** Scripts are self-contained or document dependencies clearly.

**Deterministic checks (script):**
- For `.sh` scripts: extract all `command -v` / external binary calls
- For `.py` scripts: extract all `import` statements, check if stdlib
- Cross-reference against skill's documented dependencies
- Check for inline comments documenting non-obvious dependencies

**Agent inspection checks:**
- Evaluate whether each script could run in a minimal container
- Check if script output is sufficient to replace agent inline reasoning

**Severity mapping:**
- Undocumented external dependency that causes silent failure → MAJOR
- Missing dependency documentation → MINOR
- Script that could be self-contained but imports unnecessarily → NIT

**Script:** `dependency_check.sh <skill-dir>`

### 4.10 D16: `duplication-detection`

**What it checks:** The "each fact lives in exactly one place" rule.

**Deterministic checks (script):**
- Extract all rule-like statements (lines containing SHALL/SHOULD/MUST) from
  every `.md` file
- Fuzzy-match for near-duplicate statements across files
- Check for workflow steps narrated in SKILL.md AND repeated in references
- Estimate wasted tokens from duplication

**Agent inspection checks:**
- For each detected duplicate, determine if it's intentional (fallback) or
  accidental
- Check if changes to the rule would require editing multiple files

**Severity mapping:**
- Same rule stated in 3+ places → MAJOR (maintenance hazard + token waste)
- Same rule in 2 places without cross-reference → MINOR
- Intentional duplication (fallback) without "see X" pointer → NIT

**Script:** `duplication_check.sh <skill-dir>`

### 4.11 D17: `reference-depth`

**What it checks:** Reference file sizing, nesting, and reachability.

**Deterministic checks (script):**
- Measure every reference file (lines, chars, est. tokens)
- Flag files > 300 lines
- Check for reference-to-reference links (nesting)
- Verify all references are reachable from SKILL.md
- Check for TOC in files > 300 lines

**Severity mapping:**
- Reference file links to another reference (nesting) → MAJOR
- Reference > 300 lines without TOC → MINOR
- Orphaned reference not linked from SKILL.md → MINOR
- Reference > 500 lines → MAJOR (should split)

**Script:** `reference_depth_check.sh <skill-dir>`

---

## 5. Confidence Scoring Framework

### 5.1 The Problem

Current findings have severity (BLOCKER/MAJOR/MINOR/NIT) but no confidence
dimension. A MAJOR finding backed by a failing script has very different weight
than a MAJOR finding based on an agent's pattern-matching intuition.

### 5.2 Confidence Levels

| Level | Tag | Definition | Evidence Standard |
|---|---|---|---|
| HIGH | `[H]` | Verified deterministically | Script output, exact CLI error, measurable threshold breach |
| MEDIUM | `[M]` | Verified by agent inspection | Agent traced the code path, read the file, confirmed the pattern |
| LOW | `[L]` | Inferred from pattern matching | Agent recognized a known anti-pattern but did not fully trace |

### 5.3 Rules for Assignment

You SHALL assign confidence as follows:

- WHEN a finding is produced by a deterministic script (exit code, measured
  value, regex match), confidence SHALL be HIGH.
- WHEN a finding is produced by agent inspection where the agent read the
  specific file and traced the specific issue, confidence SHALL be MEDIUM.
- WHEN a finding is produced by pattern recognition without full trace (e.g.,
  "this looks like it might have CRLF" without running the check), confidence
  SHALL be LOW.
- IF a finding has LOW confidence, you SHALL note what additional verification
  would raise it to MEDIUM or HIGH.

### 5.4 Confidence in the Report

Findings format changes from:
```
### M1: Name mismatch in domain table
- **Severity:** MAJOR
```

To:
```
### M1: Name mismatch in domain table
- **Severity:** MAJOR
- **Confidence:** HIGH — verified by executing `mpcr protocol dispatch --role architecture` and observing error
```

The executive summary SHALL include confidence distribution:
```
**Finding counts:** 0 BLOCKER, 3 MAJOR, 5 MINOR, 2 NIT
**Confidence:** 6 HIGH, 3 MEDIUM, 1 LOW
```

### 5.5 Confidence-Gated Verdicts

The ship-readiness verdict SHALL account for confidence:

- A BLOCKER at HIGH confidence → hard block, no override.
- A BLOCKER at LOW confidence → block WITH note: "verify before shipping."
- A MAJOR at LOW confidence SHALL NOT count toward the SHIP_WITH_FIXES
  threshold unless the agent provides a path to raise confidence.

### 5.6 Aggregate Confidence Score

WHEN the report is finalized, compute an aggregate confidence score:

```
aggregate = (HIGH_count × 3 + MEDIUM_count × 2 + LOW_count × 1) / (total_findings × 3)
```

Report as a percentage. Interpretation:
- ≥ 80% → "High-confidence audit" — findings are well-grounded
- 50-79% → "Mixed-confidence audit" — some findings need verification
- < 50% → "Low-confidence audit" — many findings are pattern-guesses

---

## 6. EARS Compliance Check (New Domain)

### 6.1 What is EARS

EARS (Easy Approach to Requirements Syntax) is a structured syntax for writing
unambiguous requirements. It uses conditional keywords to eliminate ambiguity:

| Pattern | Template | Example |
|---|---|---|
| Ubiquitous | You SHALL/SHALL NOT `<action>`. | You SHALL use LF line endings. |
| Event-driven | WHEN `<trigger>` THEN you SHALL `<action>`. | WHEN a script fails THEN you SHALL record the error. |
| State-driven | WHILE `<state>` you SHALL `<action>`. | WHILE workers are running you SHALL enforce the concurrency cap. |
| Unwanted behavior | IF `<condition>` THEN you SHALL `<response>`. | IF output exceeds 5000 chars THEN you SHALL add a compact mode. |
| Optional | You MAY `<action>`. | You MAY spawn explorer subagents. |
| Iterative | WHILE `<items exist>` THEN you SHALL `<action>`. WHEN `<none found>` THEN you SHALL stop. | WHILE new domains are discovered THEN you SHALL add them. WHEN none are found THEN you SHALL stop. |

### 6.2 Why EARS Matters for Skills

Agent instructions written in natural prose are the #1 source of ambiguity.
"Make sure scripts work" is not actionable. "You SHALL execute every script
with `--help` and record the exit code" is. EARS provides a framework for
identifying which instructions are precise and which are vague.

### 6.3 What This Domain Checks

The EARS check is NOT about converting everything to EARS. It is about
identifying instructions that would BENEFIT from EARS structure — places where
an agent is likely to misinterpret because the directive is ambiguous.

**Deterministic checks (script):**
- Count lines containing SHALL/SHALL NOT/SHOULD/MAY (EARS-compatible)
- Count imperative instructions without these keywords
- Calculate EARS coverage ratio: `EARS_lines / total_directive_lines`
- Identify imperative sentences that lack conditions (potential ubiquitous reqs
  that might actually be conditional)
- Detect instructions using "make sure", "ensure", "try to", "be careful",
  "consider" — vague directives that resist deterministic interpretation

**Agent inspection checks:**
- For each non-EARS directive, evaluate:
  - Is this genuinely ubiquitous (always applies)? → Fine as-is with SHALL.
  - Is there a hidden condition? → Flag for WHEN/IF conversion.
  - Is this aspirational rather than testable? → Flag as non-requirement.
- Identify the top-5 highest-ambiguity instructions and suggest EARS rewrites

**Severity mapping:**
- EARS coverage < 30% in instruction-heavy files → MAJOR (high ambiguity risk)
- Vague directive in a critical path (workflow step, dispatch) → MAJOR
- Vague directive in supplementary text → MINOR
- Missing condition on what appears conditional → MINOR
- Style preference (could use EARS but prose is unambiguous) → NIT

**Script:** `ears_check.sh <skill-dir>`

```
Output format:
═══ EARS Compliance Check: code-review ═══

── Summary ──
  Directive lines (SHALL/SHOULD/MAY/SHALL NOT): 47
  Conditional directives (WHEN/IF/WHILE/UNTIL):  23
  Bare imperatives (no EARS keyword):            31
  EARS coverage: 60.3%

── Vague Directive Candidates ──
  SKILL.md:45   "Make sure the workspace is clean"
  SKILL.md:89   "Try to keep outputs small"
  references/audit-phases.md:112  "Be thorough in your analysis"

── Missing Condition Candidates ──
  SKILL.md:67   "Delete temporary files" → WHEN? Always? On success only?
  SKILL.md:134  "Spawn explorer subagents" → WHEN? What triggers this?

── EARS-Compliant Highlights ──
  SKILL.md:23   "You SHALL execute every script with --help" ✓
  SKILL.md:56   "WHEN 8 agents are running THEN you SHALL wait" ✓
```

### 6.4 EARS in the Audit Report

The EARS domain produces a dedicated section in the report:

```markdown
## EARS Compliance Analysis

**Coverage:** 60.3% of directive lines use EARS keywords
**Rating:** MODERATE — core workflow is well-structured, supplementary
instructions have ambiguity pockets

### Top Ambiguity Risks

| # | Location | Current Text | Suggested EARS Rewrite | Severity |
|---|---|---|---|---|
| 1 | SKILL.md:45 | "Make sure the workspace is clean" | "WHEN starting a new audit THEN you SHALL create a fresh workspace directory" | MINOR |
| 2 | ... | ... | ... | ... |
```

### 6.5 EARS for Applicators (Suggestion Mode)

WHEN the auditor is used in conjunction with an applicator workflow, the EARS
findings SHALL be presented as SUGGESTIONS, not hard requirements:

- The applicator SHOULD rewrite vague directives using EARS patterns.
- The applicator SHALL NOT rewrite prose that is already unambiguous just to
  add EARS keywords.
- The applicator SHALL preserve the author's intent — EARS is a structural
  improvement, not a content change.

---

## 7. Prompt Complexity Analysis (New Domain)

### 7.1 Motivation

Dispatch prompts and SKILL.md instructions can be individually correct but
collectively overwhelming. An agent receiving a 3,000-char prompt with 15
nested conditions, 8 role constraints, and 4 output templates will perform
worse than one receiving the same content structured for incremental processing.

### 7.2 Complexity Dimensions

| Dimension | What It Measures | Metric |
|---|---|---|
| **Conditional density** | How many conditions per paragraph | conditions / paragraphs |
| **Nesting depth** | Deepest IF/WHEN nesting level | max indent level of conditional logic |
| **Role switching** | How many distinct behavioral modes | count of IF/WHEN role-detection blocks |
| **Output template count** | How many different output formats | count of distinct templates/formats |
| **Cross-reference load** | How many "see X" / "read Y" pointers | count of file references in instructions |
| **Negation density** | How many SHALL NOT / do NOT rules | negations / total directives |
| **Working memory demand** | How many IDs/values agent must track | count of placeholder variables |

### 7.3 Complexity Score

Each dimension gets a raw score. The aggregate complexity score is:

```
complexity = Σ(dimension_score × weight) / max_possible
```

Weights (tunable, these are starting points):

| Dimension | Weight | Threshold (MINOR) | Threshold (MAJOR) |
|---|---|---|---|
| Conditional density | 2 | > 3 per paragraph | > 6 per paragraph |
| Nesting depth | 3 | > 3 levels | > 5 levels |
| Role switching | 2 | > 3 modes | > 5 modes |
| Output template count | 1 | > 3 templates | > 6 templates |
| Cross-reference load | 1 | > 5 references | > 10 references |
| Negation density | 2 | > 30% negations | > 50% negations |
| Working memory demand | 3 | > 5 tracked values | > 8 tracked values |

### 7.4 Deterministic Checks (Script)

**Script:** `prompt_complexity_check.sh <skill-dir>`

The script measures:
- Line counts and character counts per file
- Conditional keyword frequency (WHEN/IF/WHILE/UNTIL/THEN)
- SHALL NOT / do NOT frequency
- Cross-reference frequency (links, file references)
- Placeholder variable count (`<PLACEHOLDER>`, `$VAR`, `{VAR}`)
- Indentation depth analysis for nested conditionals

```
Output format:
═══ Prompt Complexity Analysis: code-review ═══

── Per-File Metrics ──
  File                        Cond  Nest  Roles  Templ  Xref  Neg  Vars  Score
  SKILL.md                     23    3      4      2      5    12   6     62/100
  references/reviewer.md       31    4      2      3      8    15   8     74/100
  references/applicator.md     18    2      1      2      3     9   5     48/100

── Hotspots ──
  references/reviewer.md:45-78   Conditional density: 8/para  [MAJOR]
  SKILL.md:89-95                 Nesting depth: 4 levels      [MINOR]

── Aggregate ──
  Weighted complexity score: 61/100
  Rating: MODERATE
  Highest risk: conditional density in reviewer protocol
```

### 7.5 Agent Inspection Checks

Beyond the script measurements, the auditing agent SHALL evaluate:

- Can a worker subagent follow the dispatch prompt without re-reading it?
- Are there "trap" instructions where two conditions could conflict?
- Is the output template self-explanatory or does it require context from
  earlier in the document?
- Could any section be split into a separate step/phase to reduce peak
  cognitive load?

### 7.6 Complexity in the Report

```markdown
## Prompt Complexity Analysis

**Aggregate Score:** 61/100 (MODERATE)

| Dimension | Score | Rating |
|---|---|---|
| Conditional density | 4.2/para | ⚠ MINOR |
| Nesting depth | 4 levels | ⚠ MINOR |
| Working memory | 6 values | ✓ OK |
| ... | ... | ... |

### Recommendations
1. Split reviewer protocol Phase 4 (45 lines of nested conditions) into
   two sub-phases to reduce peak conditional density.
2. Extract output templates into a separate reference file loaded only
   at synthesis time.
```

---

## 8. Self-Compliance Analysis

This section audits the skill-auditor itself against every AGENTS.md rule it
will enforce. The implementer SHALL address each finding before shipping.

### 8.1 D1: `file-hygiene`

| Check | Status | Finding |
|---|---|---|
| CRLF in scripts | ✅ PASS | Both `.sh` scripts use LF |
| Shebang validity | ✅ PASS | `#!/usr/bin/env sh` on both scripts |
| Execute permissions | ✅ PASS | Both scripts are `+x` |
| CRLF in markdown | ✅ PASS | All `.md` files use LF |

**Confidence:** HIGH (verified by running `surface_check.sh` on self)

### 8.2 D2: `frontmatter-validity`

| Check | Status | Finding |
|---|---|---|
| `name` matches directory | ✅ PASS | `skill-auditor` matches `skills/skill-auditor/` |
| `name` format | ✅ PASS | Lowercase, hyphens, 13 chars |
| `description` present | ✅ PASS | Present and substantive |
| `description` ≤ 1024 chars | ✅ PASS | ~420 chars |

**Confidence:** HIGH (deterministic)

### 8.3 D3: `description-quality`

| Check | Status | Finding |
|---|---|---|
| Contains "Use when" | ✅ PASS | "Use when auditing, evaluating, or health-checking..." |
| Trigger conditions listed | ✅ PASS | Lists 6 specific trigger scenarios |
| Action verbs present | ✅ PASS | auditing, evaluating, testing, measuring, checking, simulating, producing |
| Word count ≥ 30 | ✅ PASS | ~65 words |

**Finding:** Description does not mention the NEW domains (EARS, prompt
complexity, confidence scoring). After implementation, the description SHALL
be updated to include these trigger keywords.

**Severity:** MINOR (post-implementation fix)
**Confidence:** HIGH

### 8.4 D4: `path-token-usage`

| Check | Status | Finding |
|---|---|---|
| SKILL.md uses `<skills-file-root>` | ✅ PASS | All script/reference paths use the token |
| References use relative paths | ✅ PASS | Internal links are relative |
| No hardcoded absolute paths | ✅ PASS | No absolute paths found |

**Confidence:** HIGH (grep-verified)

### 8.5 D6: `command-isolation`

| Check | Status | Finding |
|---|---|---|
| No cross-command env-var assumptions | ✅ PASS | Scripts are standalone, single invocation |
| CLI flags preferred | ✅ PASS | All scripts use positional args and `--flags` |

**Confidence:** MEDIUM (inspected, not exhaustively tested)

### 8.6 D8: `progressive-disclosure`

| Check | Status | Finding |
|---|---|---|
| SKILL.md is a router | ✅ PASS | Routes to audit-phases.md, multi-agent-audit.md, report-template.md |
| SKILL.md < 500 lines | ✅ PASS | 178 lines |
| Reference index present | ✅ PASS | Table at bottom of SKILL.md |
| Each reference < 300 lines | ✅ PASS | audit-phases: 285, multi-agent: 195, report-template: 130 |
| No reference-to-reference links | ✅ PASS | All references are leaf nodes |
| Peak context < 12,000 tokens | ✅ PASS | SKILL.md (~4,500) + audit-phases (~7,100) = ~11,600 |

**Finding:** Peak context is very close to the 12,000 token guideline at
~11,600 tokens. When new domains are added (EARS, prompt complexity), the
audit-phases.md reference will grow. The implementer SHALL split audit-phases.md
into two files or move the new domains into separate reference files to stay
under budget.

**Severity:** MAJOR (will breach context budget after expansion)
**Confidence:** HIGH (measured)

### 8.7 D9: `dispatch-prompt-quality`

| Check | Status | Finding |
|---|---|---|
| N/A | N/A | skill-auditor does not dispatch subagents |

**Note:** If the expanded auditor uses subagent dispatch for parallel domain
checking (recommended for large audits), this domain becomes applicable.

### 8.8 D10: `output-size-discipline`

| Check | Status | Finding |
|---|---|---|
| `surface_check.sh` output size | ✅ PASS | Typically < 1,000 chars |
| `measure_context.sh` output size | ✅ PASS | Typically < 2,000 chars |

**Confidence:** MEDIUM (tested on self, not on very large skills)

### 8.9 D11: `cold-start-readiness`

| Check | Status | Finding |
|---|---|---|
| Scripts run immediately | ✅ PASS | Shell scripts, no compilation needed |
| No external dependencies | ✅ PASS | Uses only POSIX utilities (find, wc, grep, head, sed, awk) |
| First run < 5 seconds | ✅ PASS | ~0.5s for surface_check, ~0.3s for measure_context |

**Confidence:** HIGH (timed)

### 8.10 D12: `script-self-containment`

| Check | Status | Finding |
|---|---|---|
| `surface_check.sh` deps | ✅ PASS | POSIX only: find, grep, wc, head, tr, sed |
| `measure_context.sh` deps | ✅ PASS | POSIX only: find, wc, awk, head |
| No undocumented deps | ✅ PASS | |

**Confidence:** HIGH (inspected script source)

### 8.11 D14: `ears-compliance` (Self-Assessment)

This is the critical self-assessment. The auditor's own instructions are
analyzed for EARS compliance.

#### SKILL.md EARS Analysis

| Line Range | Instruction | EARS? | Assessment |
|---|---|---|---|
| 16-19 | "The goal is to find every way a skill can fail..." | ❌ | Prose description, not a directive — acceptable as context |
| 38-42 | "You work through them in order because later phases depend on earlier findings" | ❌ | Missing condition: WHEN. Should be: "You SHALL work through phases in order WHEN later phases depend on earlier findings." |
| 48-49 | "Read `<sfr>/references/audit-phases.md` for detailed instructions" | ⚠ | Implicit directive. Should be: "You SHALL read `<sfr>/references/audit-phases.md` before starting Phase 1." |
| 52-53 | "Identify the skill to audit" | ⚠ | Bare imperative. Better: "You SHALL identify the skill to audit from the user's request." |
| 54-55 | "Read the skill's SKILL.md end-to-end" | ⚠ | Bare imperative. Better: "You SHALL read the target skill's SKILL.md end-to-end before executing anything." |
| 57-58 | "Read the audit phase instructions" | ⚠ | Same pattern — bare imperative. |
| 60-61 | "Create a fresh workspace" | ⚠ | Same pattern. Better: "You SHALL create a fresh workspace in a writable temporary directory." |
| 62 | "Start Phase 1" | ⚠ | Same pattern. |
| 63-64 | "Accumulate findings in a running report file" | ⚠ | Better: "You SHALL accumulate findings in a running report file as you discover them — you SHALL NOT wait until the end." |
| 65-66 | "Finalize the report using the template" | ⚠ | Better: "WHEN all phases are complete THEN you SHALL finalize the report using the template." |
| 78-79 | "A finding's severity should reflect the worst realistic outcome" | ⚠ | "should" → "SHALL". Missing: "for an agent encountering it." |
| 100-102 | "Spend your time where the skill's complexity lives" | ❌ | Aspirational — not a testable directive |
| 103-108 | Multi-agent detection bullets | ✅ | Well-structured condition list |
| 139-140 | "Both scripts are self-contained and produce structured output" | ✅ | Factual statement |

**EARS Coverage for SKILL.md:** ~35% of directive lines use EARS keywords.
The "Getting started" section (lines 52-66) is almost entirely bare imperatives.

**Recommended rewrites for Getting Started section:**

```
Current (lines 52-66):
1. Identify the skill to audit.
2. Read the skill's SKILL.md end-to-end.
3. Read the audit phase instructions.
4. Create a fresh workspace.
5. Start Phase 1.
6. Accumulate findings as you go.
7. Finalize the report.

Proposed EARS rewrite:
1. You SHALL identify the target skill from the user's request or prompt context.
2. You SHALL read the target skill's SKILL.md end-to-end to build a mental model.
   You SHALL NOT execute anything during this step.
3. You SHALL read `<sfr>/references/audit-phases.md` before starting Phase 1.
4. You SHALL create a fresh workspace in a writable directory (e.g., `/tmp/audit-workspace/`).
   You SHALL NOT modify the target skill's directory.
5. You SHALL start Phase 1 and proceed through each phase in order.
6. You SHALL write findings to a running report file as you discover them.
   You SHALL NOT defer finding documentation until report finalization.
7. WHEN all phases are complete THEN you SHALL finalize the report using
   `<sfr>/references/report-template.md`.
```

#### audit-phases.md EARS Analysis

| Section | EARS Coverage | Assessment |
|---|---|---|
| Phase 1 steps | ~50% | Mix of bare imperatives and structured instructions |
| Phase 2 steps | ~65% | Better — uses "For each" pattern as implicit iteration |
| Phase 3 steps | ~40% | "Follow the documented workflow step-by-step" is vague |
| Phase 4 steps | ~55% | Measurement steps are naturally structured |
| Phase 5 steps | ~45% | "Compare for consistency" lacks conditions |
| Ambiguity scoring | ✅ ~90% | Well-structured 1-3 scale with clear conditions |
| Time management | ✅ ~80% | Table-driven, clear thresholds |

**Overall EARS coverage for audit-phases.md:** ~55%

#### multi-agent-audit.md EARS Analysis

| Section | EARS Coverage | Assessment |
|---|---|---|
| Step 1: Inventory | ~60% | "Map every role" is imperative but clear |
| Step 2: Prompt inspection | ~70% | Good use of question-based checks |
| Step 3: Cross-role consistency | ~75% | Quantitative thresholds are inherently EARS |
| Step 4: Interface evaluation | ~50% | "Test the handoff points" is vague |
| Step 5: Context amplification | ~65% | Formula-driven, naturally structured |

**Overall EARS coverage for multi-agent-audit.md:** ~65%

### 8.12 D15: `prompt-complexity` (Self-Assessment)

| File | Cond Density | Nest Depth | Xref Load | Neg Density | Assessment |
|---|---|---|---|---|---|
| SKILL.md | 1.2/para | 2 | 5 refs | 12% | ✅ LOW — clean router |
| audit-phases.md | 2.8/para | 3 | 3 refs | 18% | ✅ MODERATE — acceptable for detailed procedures |
| multi-agent-audit.md | 3.1/para | 3 | 2 refs | 15% | ✅ MODERATE — dense but well-structured |
| report-template.md | 0.3/para | 1 | 0 refs | 5% | ✅ LOW — pure template |

**Aggregate complexity:** MODERATE (no MAJOR hotspots)

### 8.13 D16: `duplication-detection`

| Duplicated Content | Locations | Assessment |
|---|---|---|
| Severity framework (BLOCKER/MAJOR/MINOR/NIT) | SKILL.md + audit-phases.md (finding format) | MINOR — SKILL.md has the definitions, audit-phases.md has the format template. These serve different purposes but the severity names appear in both. Acceptable. |
| Phase names and budgets | SKILL.md overview table + audit-phases.md headings | NIT — Intentional (SKILL.md is the summary, audit-phases.md is the detail). |
| Script descriptions | SKILL.md script table + script `--help` output | NIT — Intentional redundancy for discoverability. |

**Finding:** No significant duplication. The three-layer model is well-followed.

**Confidence:** MEDIUM (manual inspection)

### 8.14 D17: `reference-depth`

| File | Lines | Est. Tokens | Has TOC | Nested Links |
|---|---|---|---|---|
| audit-phases.md | 285 | ~7,100 | ✅ | None |
| multi-agent-audit.md | 195 | ~4,875 | ❌ (under 300) | None |
| report-template.md | 130 | ~3,250 | ❌ (under 300) | None |

**Finding:** All references are within bounds. audit-phases.md is close to the
300-line guideline at 285 lines. After expansion with new domains, it WILL
exceed 300 lines. The implementer SHALL add a TOC and consider splitting.

**Severity:** MINOR (pre-emptive)
**Confidence:** HIGH (measured)

### 8.15 Self-Compliance Summary

| Domain | Status | Findings |
|---|---|---|
| D1 file-hygiene | ✅ PASS | 0 |
| D2 frontmatter-validity | ✅ PASS | 0 |
| D3 description-quality | ⚠ MINOR | 1 (update description post-expansion) |
| D4 path-token-usage | ✅ PASS | 0 |
| D6 command-isolation | ✅ PASS | 0 |
| D8 progressive-disclosure | ⚠ MAJOR | 1 (context budget will breach after expansion) |
| D10 output-size-discipline | ✅ PASS | 0 |
| D11 cold-start-readiness | ✅ PASS | 0 |
| D12 script-self-containment | ✅ PASS | 0 |
| D14 ears-compliance | ⚠ MINOR | SKILL.md at ~35% EARS coverage; Getting Started section needs rewrite |
| D15 prompt-complexity | ✅ PASS | 0 |
| D16 duplication-detection | ✅ PASS | 0 |
| D17 reference-depth | ⚠ MINOR | 1 (audit-phases.md close to limit, needs split post-expansion) |

**Totals:** 0 BLOCKER, 1 MAJOR, 3 MINOR, 0 NIT
**Verdict:** SHIP WITH FIXES — address the context budget issue during implementation.

---

## 9. Implementation Plan

### 9.1 Phase 1: Core Framework Changes

**Priority:** HIGH — do first, everything builds on this.

1. **Update SKILL.md** to add domain-based routing:
   - Add "Audit Domains" section with the D1-D17 table
   - Add domain activation rules
   - Add confidence scoring section (brief — details in reference)
   - Rewrite "Getting started" section to use EARS syntax
   - Keep SKILL.md under 250 lines (it's currently 178; budget ~70 lines)

2. **Split audit-phases.md** into two files:
   - `references/audit-phases-core.md` — Phases 1-3 (existing)
   - `references/audit-phases-analysis.md` — Phases 4-5 (existing)
   - This prevents context budget breach when new domains are added

3. **Create `references/domains.md`** — the domain reference:
   - Full D1-D17 domain specifications
   - Severity mappings per domain
   - Script cross-references
   - EARS check rubric
   - Prompt complexity rubric
   - Loaded conditionally: agent reads only the domains activated for the
     current audit

4. **Create `references/confidence-scoring.md`** — confidence framework:
   - Confidence levels, assignment rules, gated verdicts
   - Aggregate score formula
   - Report format changes

5. **Update `references/report-template.md`**:
   - Add confidence column to all finding tables
   - Add EARS compliance section
   - Add prompt complexity section
   - Add aggregate confidence score to executive summary
   - Add domain coverage ledger

### 9.2 Phase 2: Deterministic Scripts

**Priority:** HIGH — scripts are the backbone of HIGH-confidence findings.

New scripts to implement:

| Script | Domains | Estimated Complexity |
|---|---|---|
| `frontmatter_check.sh` | D2 | Low (~80 lines) — YAML parsing with sed/awk |
| `description_check.sh` | D3 | Low (~60 lines) — word count, pattern matching |
| `path_token_check.sh` | D4 | Low (~50 lines) — grep for hardcoded paths |
| `name_consistency_check.sh` | D5 | Medium (~150 lines) — needs CLI binary |
| `error_quality_check.sh` | D7 | Medium (~120 lines) — needs CLI binary |
| `output_size_check.sh` | D10 | Medium (~100 lines) — needs CLI binary |
| `staleness_check.sh` | D21 | Medium (~180 lines) — safe example extraction + runtime comparison |
| `cold_start_check.sh` | D11 | Low (~60 lines) — timing wrapper |
| `dependency_check.sh` | D12 | Medium (~100 lines) — import/command extraction |
| `ears_check.sh` | D14 | Medium (~150 lines) — keyword counting, pattern detection |
| `prompt_complexity_check.sh` | D15 | Medium (~130 lines) — multi-dimension analysis |
| `duplication_check.sh` | D16 | High (~200 lines) — fuzzy matching across files |
| `reference_depth_check.sh` | D17 | Low (~80 lines) — size measurement, link extraction |

**Total:** ~1,460 lines of new shell scripts.

Existing scripts to extend:
- `surface_check.sh` — no changes needed (already covers D1)
- `measure_context.sh` — extend to report per-domain context budgets

### 9.3 Phase 3: Agent Inspection Enhancements

**Priority:** MEDIUM — improves MEDIUM-confidence findings.

1. **Update audit-phases-core.md** to integrate domain checks into each phase:
   - Phase 1 now runs D1, D2, D4, D11, D12 scripts
   - Phase 2 now runs D5, D7, D10, D21 scripts (if CLI available)
   - Phase 3 now includes D6 inspection
   - Phase 4 now includes D8, D16, D17 checks
   - Phase 5 now includes D14, D15 checks

2. **Add domain-specific inspection guides** to `references/domains.md`:
   - For each domain, list the agent inspection checks
   - Include example findings with confidence levels
   - Include EARS-rewrite examples for D14

### 9.4 Phase 4: Integration and Self-Test

**Priority:** MEDIUM — validates the expansion.

1. Run the expanded auditor against itself (meta-audit)
2. Run against `code-review` skill (complex, multi-agent)
3. Run against `docker-architect` skill (simpler, reference-heavy)
4. Verify all new scripts produce clean, compact output
5. Verify context budget stays under 12,000 tokens at peak
6. Update the description in frontmatter to cover new domains

---

## 10. File Structure

### 10.1 Post-Implementation Structure

```
skills/skill-auditor/
├── SKILL.md                              (~250 lines — router + domain table)
├── references/
│   ├── audit-phases-core.md              (~200 lines — Phases 1-3)
│   ├── audit-phases-analysis.md          (~150 lines — Phases 4-5)
│   ├── domains.md                        (~320 lines — all 21 domain specs)
│   ├── confidence-scoring.md             (~80 lines — scoring framework)
│   ├── multi-agent-audit.md              (~195 lines — unchanged)
│   └── report-template.md               (~180 lines — expanded with new sections)
└── scripts/
    ├── measure_context.sh                (existing, extended)
    ├── surface_check.sh                  (existing, unchanged)
    ├── frontmatter_check.sh              (new)
    ├── description_check.sh              (new)
    ├── path_token_check.sh               (new)
    ├── name_consistency_check.sh         (new)
    ├── error_quality_check.sh            (new)
    ├── output_size_check.sh              (new)
    ├── staleness_check.sh                (new)
    ├── cold_start_check.sh               (new)
    ├── dependency_check.sh               (new)
    ├── ears_check.sh                     (new)
    ├── prompt_complexity_check.sh         (new)
    ├── duplication_check.sh              (new)
    └── reference_depth_check.sh          (new)
```

### 10.2 Context Budget Projection

| Component | Est. Tokens | Loaded When |
|---|---|---|
| SKILL.md (expanded) | ~5,000 | Always (skill trigger) |
| audit-phases-core.md | ~5,000 | Before Phase 1 |
| audit-phases-analysis.md | ~3,750 | Before Phase 4 |
| domains.md (full) | ~7,500 | Domain activation (partial load possible) |
| confidence-scoring.md | ~2,000 | Report finalization |
| multi-agent-audit.md | ~4,875 | Only for multi-agent skills |
| report-template.md | ~4,500 | Report finalization |

**Peak context scenarios:**
- Simple audit: SKILL.md + audit-phases-core.md = ~10,000 tokens ✅
- Full audit at Phase 1-3: SKILL.md + audit-phases-core.md + domains.md (partial, ~3,000) = ~13,000 tokens ⚠ (borderline)
- Full audit at Phase 4-5: SKILL.md + audit-phases-analysis.md + confidence-scoring.md = ~10,750 tokens ✅
- Report finalization: SKILL.md + report-template.md + confidence-scoring.md = ~11,500 tokens ✅
- Multi-agent: SKILL.md + audit-phases-core.md + multi-agent-audit.md = ~14,875 tokens ⚠

**Mitigation for borderline cases:**
- domains.md SHALL support partial loading (agent reads only activated domains)
- SKILL.md SHALL instruct: "WHEN entering Phase 4, you MAY unload Phase 1-3
  reference from context."
- Multi-agent audit already has its own reference file, so peak is acceptable
  (agent is done with core phases when it loads multi-agent reference)

---

## 11. Script Specifications

### 11.1 Common Conventions

All new scripts SHALL follow these conventions:

- Shebang: `#!/usr/bin/env sh`
- Line endings: LF only
- Permissions: `chmod +x`
- POSIX-compliant (no bashisms)
- Self-contained (no external dependencies beyond coreutils)
- Structured output with `═══`, `──`, `✓`/`✗`/`⚠` markers
- Exit code 0 always (findings are in output, not exit status)
- `--help` flag support
- Single positional arg: `<skill-dir>`
- Optional flags for CLI-dependent checks: `--cli <binary>`
- Output sized for agent consumption (< 3,000 chars typical)

### 11.2 Key Script: `ears_check.sh`

**Input:** `<skill-dir>`

**Algorithm:**
1. Find all `.md` files in skill directory
2. For each file:
   a. Extract lines containing directive keywords: SHALL, SHALL NOT, SHOULD,
      SHOULD NOT, MAY, MUST, MUST NOT
   b. Extract lines containing conditional keywords: WHEN, IF, WHILE, UNTIL, THEN
   c. Extract bare imperative lines: sentences starting with a verb in
      imperative mood without EARS keywords
   d. Extract vague directive lines: containing "make sure", "ensure", "try to",
      "be careful", "consider", "remember to"
3. Calculate EARS coverage: `(directive_lines + conditional_lines) / (directive_lines + conditional_lines + bare_imperatives + vague_directives)`
4. Report per-file breakdown and aggregate
5. List top-5 vague directives with line numbers
6. List top-5 missing-condition candidates with line numbers

**Bare imperative detection heuristic:**
Lines that start with a verb (after optional list marker) and don't contain
EARS keywords. This is inherently fuzzy. The script uses a curated verb list:
`run`, `execute`, `check`, `verify`, `test`, `create`, `build`, `write`,
`read`, `open`, `close`, `delete`, `remove`, `add`, `update`, `set`, `get`,
`find`, `search`, `scan`, `measure`, `compare`, `evaluate`, `produce`,
`generate`, `compile`, `install`, `configure`, `deploy`, `validate`.

### 11.3 Key Script: `prompt_complexity_check.sh`

**Input:** `<skill-dir>`

**Algorithm:**
1. Find all `.md` files in skill directory
2. For each file:
   a. Count conditional keywords (WHEN/IF/WHILE/UNTIL/THEN)
   b. Count paragraphs (blocks separated by blank lines)
   c. Calculate conditional density: `conditionals / paragraphs`
   d. Measure max indentation depth of conditional blocks
   e. Count SHALL NOT / do NOT / MUST NOT (negation density)
   f. Count cross-references (`<skills-file-root>`, `references/`, links)
   g. Count placeholder variables (`<PLACEHOLDER>`, `$VAR`, `{VAR}`)
3. Calculate per-file scores using weighted formula
4. Identify hotspots (paragraphs with density > threshold)
5. Report per-file metrics table and aggregate score

### 11.4 Key Script: `duplication_check.sh`

**Input:** `<skill-dir>`

**Algorithm:**
1. Extract all lines containing SHALL/SHOULD/MAY/MUST from every `.md` file
2. Normalize: lowercase, strip leading whitespace, remove markdown formatting
3. For each pair of files, compute line-level Jaccard similarity on
   normalized directive lines
4. Flag pairs with > 30% overlap as potential duplication
5. For each flagged pair, list the overlapping directives
6. Estimate wasted tokens: `overlapping_chars / 4`

**Note:** This uses exact and near-exact matching (after normalization), not
semantic similarity. False positives are acceptable — the agent does the
semantic evaluation.

---

## 12. Migration Notes

### 12.1 Backward Compatibility

The expanded auditor SHALL remain backward-compatible:

- Existing `surface_check.sh` and `measure_context.sh` are unchanged
- Existing phases 1-5 workflow still works
- New domains are additive, not replacing existing checks
- Reports generated by the old auditor are still valid

### 12.2 Incremental Adoption

The implementer MAY ship in stages:

1. **Stage 1:** Split audit-phases.md, add confidence scoring to report
   template, rewrite SKILL.md Getting Started in EARS
2. **Stage 2:** Add deterministic scripts (D2, D3, D4, D17 first — easiest)
3. **Stage 3:** Add EARS and prompt complexity scripts (D14, D15)
4. **Stage 4:** Add CLI-dependent scripts (D5, D7, D10, D11)
5. **Stage 5:** Add duplication and dependency scripts (D16, D12)
6. **Stage 6:** Full integration test on 3+ skills, update description

### 12.3 Risks

| Risk | Mitigation |
|---|---|
| Context budget breach with all new references | Partial loading + phase-gated reference swapping |
| New scripts have false positives | Scripts report candidates; agent makes final call |
| EARS check over-flags natural prose | EARS is a suggestion domain, not a hard gate |
| Too many domains overwhelm the audit | Domain activation rules limit to relevant subset |
| Duplication check has low precision | Jaccard on normalized directives is conservative |

### 12.4 Success Criteria

The expansion is successful when:

1. Running the auditor on `code-review` produces ≥ 10 HIGH-confidence findings
   from deterministic scripts alone
2. EARS coverage is reported for every audited skill
3. Prompt complexity scores are reported for skills with dispatch prompts
4. The auditor passes its own self-audit with zero BLOCKERs
5. Peak context stays under 12,000 tokens for the most complex audit scenario
6. All new scripts run in < 5 seconds on a typical skill directory

---

*End of architecture plan. This document is the blueprint — implementation is
a separate task.*
