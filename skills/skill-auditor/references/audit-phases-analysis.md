# Audit Phases — Analysis (Phases 4–5)

This document contains the step-by-step procedure for the analysis audit
phases (4–5). These phases focus on context efficiency and output quality —
areas that directly affect how much value an agent extracts from its limited
context window.

These phases still culminate in report writing. Deterministic checks can
quantify duplication, staleness, or token cost, but the auditor must interpret
what matters, connect it to agent impact, and fold it into the running report.

## Table of contents

- [Phase 4: Context & Token Analysis](#phase-4-context--token-analysis)
- [Phase 4b: Deterministic Duplication Gate](#phase-4b-deterministic-duplication-gate)
- [Phase 5: Output Quality](#phase-5-output-quality)
- [Time management](#time-management)

---

## Phase 4: Context & Token Analysis

**Goal:** Quantify every document's token cost and identify where the
instruction budget is spent.

Agent context windows are finite and expensive. Every unnecessary token in a
skill's instructions is a token that can't be used for the actual task.

Before moving on, ask:

- Which tokens actually help an agent succeed?
- Which disclosure layers are conditionally loaded versus always dumped up front?
- Which reductions preserve clarity and which would create ambiguity elsewhere?

### Steps

1. **Measure every document.** You SHALL measure each file in the skill directory:
   ```bash
   wc -lc <file>  # lines and characters
   ```
   Estimate tokens at roughly one token per four characters.

2. **Measure every protocol/template output.** You SHALL measure the output of any CLI that
   serves instructions through a protocol or routing subcommand, if the skill has one:
   ```bash
   tool protocol subcommand 2>&1 | wc -lc
   ```

3. **Build the context budget table:**

   | Component | Chars | Est. Tokens | Loaded When |
   |-----------|-------|-------------|-------------|
   | SKILL.md | 18,029 | ~4,500 | Always (skill trigger) |
   | protocol orchestrator | 8,246 | ~2,060 | Orchestrator start |
   | ... | ... | ... | ... |

4. **Build a candidate reduction map.** You SHALL note the places most likely
   to create waste before running the dedicated duplication gate. Examples:
   - Workflow steps repeated in `SKILL.md` and protocol outputs
   - Rules repeated in `SKILL.md` and reference documents
   - Quick-reference sections that look suspiciously close to CLI help text

5. **Calculate total context at peak.** You SHALL determine the maximum
   context an orchestrator agent would hold simultaneously. This is:
   ```
   SKILL.md + protocol outputs loaded so far + subagent results pending
   ```

6. **Propose a reduction target.** Based on the context budget and candidate reduction map, you
   SHALL estimate how much context could be cut. A good target is 40-50%
   reduction from peak.
   You SHALL list specific cuts:
   - "Remove workflow steps from SKILL.md (defer to protocol output): -2,000 tokens"
   - "Deduplicate concurrency cap across 4 documents: -400 tokens"

### What to record

- The full context budget table
- Duplication map with token estimates
- Peak context calculation
- Proposed reduction target with specific line items

### Domain scripts

For this phase, the auditor SHOULD execute these domain scripts when they
accelerate measurement or raise confidence:

- D8 (`<skills-file-root>/scripts/measure_context.sh`)
- D17 (`<skills-file-root>/scripts/reference_depth_check.sh`)

IF a script is unavailable or too weak for the observed issue, THEN the
auditor SHALL run an equivalent manual check and document that limitation in
the report.

---

## Phase 4b: Deterministic Duplication Gate

**Goal:** Run a deterministic duplication pass that separates operative
duplication from advisory duplication and uses only operative findings to
gate the audit verdict.

This gate is intentionally narrow. It provides reliable duplicate and
contradiction evidence, but it does not replace the rest of the audit report.

### Steps

1. **Run the duplication script in full scope.** You SHALL execute:
   ```bash
   <skills-file-root>/scripts/duplication_check.sh <skill-dir> --scope all --format json
   ```
   This produces the complete duplication inventory, including advisory-only
   findings that do not gate the verdict.

2. **Review the tiering.** You SHALL confirm that the script classified files
   into these buckets:
   - **Operative:** `SKILL.md`, files under `references/`, and extra markdown
     instruction files reachable from `SKILL.md` within the configured hop cap
   - **Advisory:** all other scanned markdown files

3. **Record exact duplicate groups.** You SHALL capture three categories:
   - Exact directive duplicates
   - Exact normalized instruction-block duplicates
   - Contradiction candidates

4. **Apply the gate correctly.** Only operative findings SHALL affect the
   Phase 4b gate:
   - BLOCKER / MAJOR operative findings fail the duplication gate
   - MINOR operative findings pass with required cleanup
   - Advisory-only findings remain reportable but SHALL NOT block shipment

5. **Carry deterministic confidence through the report.** Every finding from
   this phase SHALL be marked `HIGH [H]`, because it is produced by exact,
   repeatable script logic.

6. **Synthesize before verdicting.** After the script runs, the auditor SHALL
   translate gate output into report findings using the skill's real workflow
   impact. Operative duplicates can gate shipment; advisory duplicates still
   need narrative explanation when they waste context or mislead agents.

### What to record

- Gate status and highest operative severity
- Operative duplicate findings with estimated wasted tokens
- Advisory duplicate findings kept separate from gating evidence
- Contradiction candidates with the normalized key and both polarities
- Aggregate operative duplicate waste and whether it crossed a threshold

### Domain scripts

For this phase, the auditor SHOULD execute:

- D16 (`<skills-file-root>/scripts/duplication_check.sh <skill-dir> --scope all --format json`)

WHEN the script cannot run, THEN the auditor SHALL perform a manual duplicate
inventory, explicitly downgrade confidence below HIGH, and note that the gate
itself was not fully exercised.

---

## Phase 5: Output Quality

**Goal:** Are the skill's templates, dispatch prompts, and generated outputs
thorough, consistent, and tailored to their purpose?

Before moving on, ask:

- Could an agent produce a strong result from these templates without guessing?
- Do the outputs reinforce the skill's claims, or expose hypocrisy and drift?
- Which quality gaps belong in the final verdict versus as follow-up polish?

### Steps

1. **Inventory all output artifacts.** You SHALL inventory these:
   - Dispatch/worker prompts (for multi-agent skills)
   - Report templates (WHEN present)
   - Generated files (if the skill produces documents, code, configs)
   - Protocol guidance outputs

2. **Compare for consistency.** WHEN the skill has multiple variants of the
   same output type (e.g., dispatch prompts for different roles), compare:

   a. **Depth consistency:** Measure the size of each variant. Flag any that
      are less than 60% of the median size — they're likely shallow.

   b. **Structural consistency:** Do all variants follow the same template?
      Do they all have the same sections? Flag missing sections.

   c. **Domain tailoring:** Does each variant have content specific to its
      domain, or is it mostly generic boilerplate? A dispatch prompt that's
      90% shared text and 10% domain-specific is probably too generic.

3. **Fill in one template with test data.** You SHALL take the skill's primary output
   template (report template, dispatch prompt, etc.) and fill it in using
   data from your Phase 3 workflow simulation. Evaluate:
   - Are all fields clear and unambiguous?
   - Are there fields an agent would struggle to fill?
   - Does the filled template meet the quality bar described in the docs?

4. **Check for anti-laziness guardrails.** You SHALL check whether the skill includes mechanisms
   to prevent shallow or generic output. Examples:
   - Minimum counts (e.g., "at least 2 theorems per domain")
   - Specificity requirements (e.g., "must reference file:line")
   - Explicit anti-patterns (e.g., "'the code works' is NOT a valid proof")

   If these are missing, note it — agents tend toward shallow output without
   explicit depth requirements.

5. **Pressure-test reportability.** You SHALL confirm that your accumulated
   evidence can actually be expressed cleanly in the provided report template.
   If a phase or domain consistently produces evidence that the template cannot
   capture, that is itself a finding.

### What to record

- Size comparison table across variants
- Structural comparison (sections present/absent per variant)
- Domain-tailoring assessment
- Template fill-in evaluation
- Anti-laziness guardrail inventory

### Domain scripts

For this phase, the auditor SHOULD execute the following domain scripts when
they sharpen evidence:

- D14 (`<skills-file-root>/scripts/ears_check.sh`)
- D15 (`<skills-file-root>/scripts/prompt_complexity_check.sh`)

WHEN a script is not present, THEN the auditor SHALL perform the equivalent
checks manually and note the missing helper coverage as a finding.

---

## Time management

If you're working under a time constraint, here's how to allocate:

| Constraint | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|-----------|---------|---------|---------|---------|---------|
| 15 min | 3 min | 4 min | 5 min | 2 min | 1 min |
| 30 min | 5 min | 8 min | 10 min | 4 min | 3 min |
| 60 min | 8 min | 15 min | 20 min | 10 min | 7 min |
| No limit | Thorough | Exhaustive | Full simulation | Deep analysis | All variants |

When time is tight, prioritize in this order:
1. Phase 1 (a broken build blocks everything)
2. Phase 2 name consistency checks (highest-ROI single step)
3. Phase 3 primary workflow only (skip alternate modes)
4. Phase 4 SKILL.md measurement only (skip protocol outputs)
5. Phase 4b duplication gate on operative files only
6. Phase 5 size comparison only (skip template fill-in)
