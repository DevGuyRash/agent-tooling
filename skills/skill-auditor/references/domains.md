# Audit Domains Reference

This file defines the 21 audit domains (D1–D21) used by the skill-auditor
framework. Each domain specifies what to check, how findings map to severity
levels, and which scripts accelerate the work.

> **Partial-loading rule.** You SHALL load only the domains activated for the
> current audit. Scan the table of contents and the activation table below,
> then jump to the relevant `### Dnn` sections. Do not read this entire file
> up front.

---

## Table of contents

- [Domain Activation Rules](#domain-activation-rules)
- [D1: file-hygiene](#d1-file-hygiene)
- [D2: frontmatter-validity](#d2-frontmatter-validity)
- [D3: description-quality](#d3-description-quality)
- [D4: path-token-usage](#d4-path-token-usage)
- [D5: name-consistency](#d5-name-consistency)
- [D6: command-isolation](#d6-command-isolation)
- [D7: error-message-quality](#d7-error-message-quality)
- [D8: progressive-disclosure](#d8-progressive-disclosure)
- [D9: dispatch-prompt-quality](#d9-dispatch-prompt-quality)
- [D10: output-size-discipline](#d10-output-size-discipline)
- [D11: cold-start-readiness](#d11-cold-start-readiness)
- [D12: script-self-containment](#d12-script-self-containment)
- [D13: cross-skill-integration](#d13-cross-skill-integration)
- [D14: ears-compliance](#d14-ears-compliance)
- [D15: prompt-complexity](#d15-prompt-complexity)
- [D16: duplication-detection](#d16-duplication-detection)
- [D17: reference-depth](#d17-reference-depth)
- [D18: convergence](#d18-convergence)
- [D19: divergence](#d19-divergence)
- [D20: adherence](#d20-adherence)
- [D21: staleness-drift](#d21-staleness-drift)

---

## Domain Activation Rules

When the audit begins, the auditor SHALL determine which domains to activate
based on the target skill's characteristics.

| Skill characteristic                      | Activated domains   |
|-------------------------------------------|---------------------|
| **Universal** (always run)                | D1, D2, D3, D4, D8 |
| Has `scripts/` directory                  | D12                 |
| Has `references/` directory               | D16, D17            |
| Dispatches subagents                      | D9                  |
| CLI-heavy (binaries or CLIs)              | D5, D7, D10, D11   |
| Has conditional / EARS-style instructions | D14, D15            |
| Cross-skill dependencies                  | D13                 |
| Has iterative/multi-pass workflow         | D18                 |
| Produces creative/variant outputs         | D19                 |
| References AGENTS.md or external rules    | D20                 |
| **All audits** (lightweight)              | D6, D18, D20, D21   |

When the skill exhibits multiple traits, the union of all activated domains
applies. If a domain's script requires a CLI binary that is unavailable, the
auditor SHALL still perform the agent-based checks and note the missing
binary in the report.

---

## Domain Specifications

### D1: file-hygiene

**Source:** Phase 1 — Environment & Build · **Tier:** Deterministic
**Script:** `<skills-file-root>/scripts/surface_check.sh`

**Seed checks:**
- Detect CRLF line endings in all text files.
- Verify `+x` permission and correct shebangs on every script.
- Flag hidden files (`.DS_Store`, `Thumbs.db`) that SHOULD NOT be committed.
- When `.gitattributes` exists, validate its line-ending rules.

**Severity:** BLOCKER — no permission *and* no shebang on script. MAJOR — CRLF in scripts. MINOR — CRLF in non-script text. NIT — stale hidden files.

---

### D2: frontmatter-validity

**Source:** Phase 2 — API Surface · **Tier:** Deterministic
**Script:** `<skills-file-root>/scripts/frontmatter_check.sh`

**Seed checks:**
- SKILL.md begins with valid YAML frontmatter delimited by `---`.
- `name` field matches the skill directory name exactly.
- `description` field is present and non-empty.
- No unquoted YAML special characters; no keys outside the allowed set.

**Severity:** BLOCKER — missing or unparseable frontmatter. MAJOR — `name`/directory mismatch. MINOR — empty description. NIT — extra undocumented keys.

---

### D3: description-quality

**Source:** Phase 2 — API Surface · **Tier:** Heuristic+Agent
**Script:** `<skills-file-root>/scripts/description_check.sh`

**Seed checks:**
- Contains at least one trigger condition ("Use when …").
- At least two action verbs (e.g., "generate", "validate").
- Word count between 30 and 120.
- Avoids vague filler ("helps with things", "various tasks").
- When the skill has a CLI, the description SHALL mention the primary command.

**Severity:** BLOCKER — description missing. MAJOR — no trigger conditions. MINOR — word count outside range. NIT — minor filler phrases.

---

### D4: path-token-usage

**Source:** Phase 1 — Environment & Build · **Tier:** Deterministic
**Script:** `<skills-file-root>/scripts/path_token_check.sh`

**Seed checks:**
- All path references use `<skills-file-root>`, not hardcoded paths.
- No bare `./scripts/` or `../` patterns in SKILL.md or references.
- Paths in fenced code blocks retain the `<skills-file-root>` prefix.
- Referenced paths resolve to files that actually exist.

**Severity:** BLOCKER — hardcoded absolute path. MAJOR — `../` escaping the skill dir. MINOR — missing prefix. NIT — trailing slashes or casing.

---

### D5: name-consistency

**Source:** Phase 2 — API Surface · **Tier:** Agent+Script (needs CLI)
**Script:** `<skills-file-root>/scripts/name_consistency_check.sh`

**Seed checks:**
- Frontmatter name matches directory name.
- When a CLI exists, its `--help` output uses the same name.
- SKILL.md body, README, and dispatch templates use a consistent name.
- Subcommand help text names the parent skill correctly.

**Severity:** BLOCKER — CLI name differs from frontmatter. MAJOR — SKILL.md body name mismatch. MINOR — inconsistent capitalization. NIT — one-off abbreviation.

---

### D6: command-isolation

**Source:** Phase 3 — Workflow Simulation · **Tier:** Agent (grep heuristic)
**Script:** —

**Seed checks:**
- No env var set in one block and relied upon in a later block without re-export.
- `cd`, `pushd`, `export` do not leak across fenced code blocks.
- When commands share state, the dependency is documented explicitly.
- No `source`/`.` commands with side-effects crossing block boundaries.

**Severity:** BLOCKER — critical step depends on variable set blocks earlier. MAJOR — `cd` assumed across blocks. MINOR — benign export leaks. NIT — style preference.

---

### D7: error-message-quality

**Source:** Phase 2 — API Surface · **Tier:** Agent+Script (needs CLI)
**Script:** `<skills-file-root>/scripts/error_quality_check.sh`

**Seed checks:**
- Errors are short (<3 lines) and state what went wrong.
- Each error suggests a corrective action or points to docs.
- No raw stack traces leak into user-facing output.
- Exit codes are non-zero on failure; invalid args reference `--help`.

**Severity:** BLOCKER — empty error or bare stack trace. MAJOR — no corrective action. MINOR — verbose but correct. NIT — wording polish.

---

### D8: progressive-disclosure

**Source:** Phase 4 — Context & Token Analysis · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/measure_context.sh`

**Seed checks:**
- SKILL.md uses the 3-layer model: summary → workflow → deep references.
- Layer 1 (frontmatter + first 50 lines) suffices to decide skill usage.
- Layer 2 (SKILL.md body) stays under 8 KB.
- Layer 3 (references/) is loaded on demand via explicit paths.
- No single reference file exceeds 15 KB.

**Severity:** BLOCKER — SKILL.md >20 KB with no extraction. MAJOR — reference loaded unconditionally. MINOR — Layer 2 slightly >8 KB. NIT — ordering improvements.

---

### D9: dispatch-prompt-quality

**Source:** Phase 3b — Multi-Agent Audit · **Tier:** Agent
**Script:** —

**Seed checks:**
- Each dispatch prompt is self-contained (no parent SKILL.md required).
- Prompt specifies exact scope: files, directories, domains.
- Output contract defined: format, location, naming convention.
- No implicit knowledge assumed; all context inlined or path-referenced.
- When multiple subagents dispatch, their scopes SHALL NOT overlap.

**Severity:** BLOCKER — prompt references inaccessible context. MAJOR — no output contract. MINOR — slightly ambiguous scope. NIT — wording tightening.

---

### D10: output-size-discipline

**Source:** Phase 5 — Output Quality · **Tier:** Agent+Script (needs CLI)
**Script:** `<skills-file-root>/scripts/output_size_check.sh`

**Seed checks:**
- Default CLI output fits within 4 KB.
- Filtering flags exist (`--quiet`, `--json`, `--summary`).
- When output exceeds 4 KB, the tool warns or paginates.
- Structured output (JSON/YAML) available for machine consumption.
- No banners, ASCII art, or color codes in non-TTY output.

**Severity:** BLOCKER — default output >20 KB, no filter. MAJOR — no structured-output flag. MINOR — slightly >4 KB. NIT — decorative TTY elements.

---

### D11: cold-start-readiness

**Source:** Phase 1 — Environment & Build · **Tier:** Deterministic
**Script:** `<skills-file-root>/scripts/cold_start_check.sh`

**Seed checks:**
- Runs in <5 s on first invocation (no compile step).
- No `cargo build`, `npm install`, or equivalent on first use.
- When a build step is required, SKILL.md documents it with expected duration.
- Pre-built binaries or interpreted scripts preferred.
- Network access SHALL NOT be required for initial execution.

**Severity:** BLOCKER — multi-minute build with no warning. MAJOR — cold start 5–30 s. MINOR — build noise on stderr. NIT — caching opportunities.

---

### D12: script-self-containment

**Source:** Phase 1 — Environment & Build · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/dependency_check.sh`

**Seed checks:**
- External deps documented at each script's top or in SKILL.md.
- Scripts use POSIX constructs unless shebang declares a specific shell.
- No undeclared dependency on `jq`, `yq`, `python3`, etc.
- When a dep is missing at runtime, script prints a clear error and exits 1.

**Severity:** BLOCKER — silent failure on missing dep. MAJOR — dep undocumented. MINOR — bashism without bash shebang. NIT — shared preamble opportunity.

---

### D13: cross-skill-integration

**Source:** Phase 3 — Workflow Simulation · **Tier:** Agent
**Script:** —

**Seed checks:**
- Integration points with other skills documented in SKILL.md.
- Cross-skill name references match the target's frontmatter `name`.
- Shared data contracts (formats, directory conventions) are explicit.
- No circular dependencies, or resolution strategy is documented.
- Handoff context is sufficient for the receiving skill to proceed.

**Severity:** BLOCKER — circular dep causes infinite loop. MAJOR — stale/wrong skill name. MINOR — implied data format. NIT — add "Related skills" section.

---

### D14: ears-compliance

**Source:** Phase 4 — Context & Token Analysis · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/ears_check.sh`

**Seed checks:**
- EARS keywords (`SHALL`, `SHOULD`, `MAY`, `WHEN`, `IF`, `WHERE`) used
  consistently and correctly.
- Vague phrasing (for example, weak modal wording) SHALL be replaced
  with `SHALL`/`SHOULD` where the intent is a directive.
- Conditionals follow `WHEN <cond>, the system SHALL …` pattern.
- Negative requirements use `SHALL NOT`, not ambiguous phrasing.

**Severity:** BLOCKER — safety rule uses `SHOULD` instead of `SHALL`. MAJOR — vague directive on core step. MINOR — inconsistent keyword usage. NIT — style preference.

---

### D15: prompt-complexity

**Source:** Phase 4 — Context & Token Analysis · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/prompt_complexity_check.sh`

**Seed checks:**
- No instruction exceeds 2 levels of conditional nesting.
- Conditional density stays below 5 per 100 words.
- Complex decision trees extracted into tables or flowcharts.
- When a section exceeds 3 conditionals, it is split into sub-sections.

**Severity:** BLOCKER — 4+ nesting levels. MAJOR — density >5/100 in critical section. MINOR — section would benefit from a table. NIT — marginal restructuring.

---

### D16: duplication-detection

**Source:** Phase 4b — Deterministic Duplication Gate · **Tier:** Deterministic
**Script:** `<skills-file-root>/scripts/duplication_check.sh`

**Seed checks:**
- The duplication pass SHALL classify documents into **operative** and
  **advisory** tiers before scoring findings.
- Operative files include `SKILL.md`, files in `references/`, and any extra
  markdown instruction files reachable from `SKILL.md` within the configured
  hop budget. Advisory files are scanned but SHALL NOT gate the verdict.
- Exact directive-line duplicates SHALL be detected deterministically across
  files after normalization.
- Exact normalized instruction-block duplicates of 3+ non-empty lines SHALL
  be detected deterministically outside fenced code blocks.
- Contradiction candidates SHALL be detected by stripping modality and
  negation, then comparing positive vs negative variants of the same key.
- Findings SHALL be sorted deterministically so repeated runs on unchanged
  input produce byte-identical output.

**Severity:** BLOCKER — contradiction candidate across 2+ operative files.
MAJOR — exact directive duplicated across 3+ operative files; exact block
duplicate across 2+ operative files with normalized length >=160 chars; or
cumulative operative duplicate waste >=200 tokens. MINOR — exact directive
duplicate across exactly 2 operative files; exact block duplicate across 2+
operative files below the MAJOR length threshold; or cumulative operative
duplicate waste between 20 and 199 tokens. NIT — duplicates limited to
advisory files or advisory/reference extraction opportunities.

---

### D17: reference-depth

**Source:** Phase 4 — Context & Token Analysis · **Tier:** Deterministic
**Script:** `<skills-file-root>/scripts/reference_depth_check.sh`

**Seed checks:**
- No reference chain exceeds 3 hops from SKILL.md (A→B→C max).
- Every file in `references/` reachable from SKILL.md within 2 hops.
- Reference files over 300 lines SHALL include a table of contents.
- Reference files over 500 lines or 30 KB SHALL be flagged for split planning.
- Orphaned reference files (on disk but never linked) are flagged.

**Severity:** BLOCKER — chain >3 hops. MAJOR — orphaned file confuses agent, or reference >30 KB. MINOR — reference >500 lines without split plan, or >300 lines without TOC. NIT — add reference index to SKILL.md.

---

### D18: convergence

**Source:** Phase 3 — Workflow Simulation + Phase 5 — Output Quality · **Tier:** Agent
**Script:** —

**What convergence means:** Convergence measures whether repeated audit runs
on the same skill produce consistent findings. An auditor that yields
contradictory or wildly different results on successive passes has low
convergence. High convergence means the audit framework is deterministic and
reproducible — the same inputs produce the same assessments.

**Seed checks:**
- WHEN the auditor's scripts produce deterministic output, THEN repeated
  invocations on the same skill directory SHALL yield identical findings.
- WHEN agent-inferred findings appear, THEN their confidence level SHALL
  reflect the reduced reproducibility (MEDIUM or LOW, not HIGH).
- The audit framework SHALL define clear thresholds and rubrics so that two
  different agents applying the same skill-auditor against the same target
  would arrive at substantially similar findings (>80% overlap on BLOCKER
  and MAJOR findings).
- WHEN a skill has multi-pass workflows (e.g., "run Phase 1, then iterate"),
  THEN each pass SHALL narrow findings, not introduce new contradictions.
- Script outputs SHALL be idempotent: running `surface_check.sh` twice on an
  unchanged directory SHALL produce byte-identical output.

**Confidence integration:**
- A finding backed by deterministic script output has HIGH convergence
  confidence — it will reproduce on every run.
- A finding from agent inspection has MEDIUM convergence confidence — another
  agent might phrase it differently but should identify the same issue.
- A finding from pattern matching has LOW convergence confidence — it may not
  reproduce across agents or runs.

**Severity:** BLOCKER — auditor produces contradictory findings across runs on unchanged input. MAJOR — >20% variance in findings between runs. MINOR — cosmetic differences in finding descriptions. NIT — ordering differences in report output.

---

### D19: divergence

**Source:** Phase 5 — Output Quality · **Tier:** Agent
**Script:** —

**What divergence means:** Divergence measures the auditor's ability to
explore multiple solution paths, generate varied recommendations, and avoid
collapsing into generic or repetitive output. An auditor with low divergence
produces boilerplate findings that read identically regardless of the target
skill. High divergence means findings and recommendations are tailored to the
specific skill being audited.

**Seed checks:**
- WHEN the auditor produces findings, THEN each finding SHALL reference
  specific file locations, line numbers, or command outputs from the target
  skill — not generic advice.
- WHEN the auditor produces recommendations, THEN each recommendation SHALL
  be actionable for the specific skill, not a restatement of AGENTS.md rules.
- WHEN multiple domains produce findings on the same file, THEN each domain's
  findings SHALL offer a distinct perspective (not duplicated observations
  reworded).
- The auditor SHALL NOT produce identical finding text for different target
  skills. WHEN two audit reports share >60% finding text verbatim, THEN the
  auditor's domain tailoring is insufficient.
- WHEN the skill has variant outputs (e.g., dispatch prompts for multiple
  roles), THEN the auditor SHALL evaluate each variant independently and note
  specific differences — not summarize them as a group.

**Confidence integration:**
- Divergence assessment on template-generated output is HIGH confidence
  (measurable by text comparison).
- Divergence assessment on agent-written findings is MEDIUM confidence
  (requires semantic comparison, not just text matching).

**Severity:** BLOCKER — audit report is indistinguishable from a generic template with no skill-specific content. MAJOR — >40% of findings are generic AGENTS.md restatements without skill-specific evidence. MINOR — some findings lack file:line anchors. NIT — recommendation could be more specific.

---

### D20: adherence

**Source:** Phase 1 — Environment & Build + Phase 5 — Output Quality · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/ears_check.sh` (partial — EARS subset)

**What adherence means:** Adherence measures how faithfully a skill follows
the rules and constraints defined in AGENTS.md and any applicable governance
documents. Unlike other domains that check specific technical properties,
adherence is a meta-domain: it verifies that the skill has internalized
external rules as concrete, checkable properties within its own workflow.

**Seed checks:**
- WHEN AGENTS.md defines a rule (e.g., "LF line endings"), THEN the skill
  SHALL have a corresponding check that verifies compliance — either via
  script or explicit agent instruction.
- WHEN AGENTS.md defines a naming convention, THEN the skill's documentation
  and CLI SHALL use that exact convention — no paraphrasing or abbreviation.
- WHEN AGENTS.md defines a progressive disclosure model, THEN the skill's
  file structure SHALL implement that model (SKILL.md as router, references
  as just-in-time detail).
- The skill SHALL NOT contradict AGENTS.md. WHEN a skill instruction conflicts
  with AGENTS.md, THEN the conflict SHALL be flagged as a BLOCKER.
- WHEN the skill audits other skills for AGENTS.md compliance, THEN the
  auditor skill itself SHALL pass every check it applies to others
  (self-compliance).
- WHEN AGENTS.md adds new rules, THEN the skill SHALL have a mechanism
  (domain activation, script update) to absorb those rules without requiring
  a full rewrite.
- WHEN the skill suggests context reduction or instruction truncation, THEN
  the suggestion SHALL NOT degrade the quality or completeness of
  instructions that agents depend on for correct behavior. Adherence to
  instruction quality takes precedence over token savings.

**Confidence integration:**
- Rule-by-rule AGENTS.md compliance checked via script output is HIGH
  confidence.
- Structural compliance (progressive disclosure model) verified by agent
  inspection is MEDIUM confidence.
- Self-compliance assessment (auditor auditing itself) is MEDIUM confidence
  unless validated by running the auditor's own scripts against itself.

**AGENTS.md absorption checklist:**
The following AGENTS.md sections SHALL have corresponding audit checks:

| AGENTS.md Section                          | Auditor Domain(s) |
|--------------------------------------------|--------------------|
| Command isolation                          | D6                 |
| `<skills-file-root>` usage                 | D4                 |
| Frontmatter and naming                     | D2, D5             |
| Description quality                        | D3                 |
| File hygiene                               | D1                 |
| Name consistency                           | D5                 |
| Error message design                       | D7                 |
| Progressive disclosure                     | D8                 |
| Subagent dispatch prompt design            | D9                 |
| Output size discipline                     | D10                |
| Cold-start readiness                       | D11                |
| Script self-containment                    | D12                |
| Integration testing                        | D13                |
| EARS compliance (implicit in directives)   | D14                |
| Prompt complexity                          | D15                |
| Duplication detection                      | D16                |
| Reference depth                            | D17                |
| Convergence (audit reproducibility)        | D18                |
| Divergence (finding specificity)           | D19                |
| Adherence (rule absorption)               | D20                |
| Example/runtime drift                     | D21                |

WHEN an AGENTS.md section has no corresponding domain, THEN the auditor SHALL
flag this as a D20 MAJOR finding against itself.

**Severity:** BLOCKER — skill contradicts AGENTS.md rule. MAJOR — AGENTS.md rule has no corresponding audit check. MINOR — rule is checked but check is incomplete. NIT — adherence documentation could be more explicit.

---

### D21: staleness-drift

**Source:** Phase 2 — API Surface + Phase 3 — Workflow Simulation · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/staleness_check.sh`

**What staleness means:** Staleness drift measures whether skill documentation
still matches the behavior an agent sees today in the current repo state.
Unlike D7, D8, D13, or D20, this domain is not about error-message quality,
document structure, cross-skill handoffs, or AGENTS.md rule absorption. It
checks whether runnable examples, documented flags, and surrounding behavior
claims have drifted away from what the toolchain or scripts actually do.

**Seed checks:**
- Safe documented commands in `SKILL.md` and `references/` SHALL execute
  successfully against the current skill state.
- Documented script paths, flags, and subcommands used in examples SHALL
  resolve on disk or in the current CLI help output.
- The extractor SHALL aggressively include command-shaped fenced and inline
  examples, then normalize multiline continuations into one logical command.
- WHEN direct execution is unsafe or placeholders are present, the checker
  SHALL attempt `--help` or `<subcommand> --help` fallback verification before
  classifying the example as skipped.
- WHEN nearby prose claims an example "prints", "shows", "returns", "fails",
  or "succeeds", THEN the agent SHALL compare that claim against the execution
  transcript captured by `staleness_check.sh`.
- Examples that appear runnable but require hidden substitutions, setup, or
  state not mentioned in the docs SHALL be flagged as stale or underspecified.
- Behavioral contradictions between the documentation and current runtime SHALL
  be reported here even when the wording itself is otherwise clear.

**Overlap boundaries:**
- D7 owns whether errors include hints and are concise for agents.
- D8 owns whether the documentation is routed and layered efficiently.
- D13 owns cross-skill integration contracts and handoffs.
- D20 owns AGENTS.md rule absorption and self-compliance.
- D21 owns stale examples, stale behavior claims, and doc/runtime drift.

**Severity:** BLOCKER — primary workflow command or guaranteed example cannot
work as documented, or documented behavior is contradicted by current runtime
with no workable path forward. MAJOR — documented example uses missing target,
removed flag, stale subcommand, or materially incorrect behavior claim.
MINOR — example is stale because required substitution/setup context is
omitted, or the drift is recoverable with light agent inference. NIT —
optional or illustrative example drift that does not affect the main path.
