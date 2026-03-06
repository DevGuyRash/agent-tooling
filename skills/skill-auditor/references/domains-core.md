# Audit Domains — Core (D1–D13)

This file defines structural audit domains D1–D13. These cover file hygiene,
naming, error quality, progressive disclosure, dispatch prompts, output
sizing, cold-start readiness, script containment, and cross-skill integration.

> **Partial-loading rule.** You SHALL load only the domains activated for the
> current audit. Use `audit-skill domain <ID>` or scan the table of contents
> below and jump to the relevant section.

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

---

## Domain Activation Rules

When the audit begins, the auditor SHALL determine which domains to activate
based on the target skill's characteristics.

| Skill characteristic                      | Activated domains   |
|-------------------------------------------|---------------------|
| **Universal** (always run)                | D1, D2, D3, D4, D6, D8, D18, D20, D21 |
| Has `scripts/` directory                  | D12, D23            |
| Has `references/` directory               | D16, D17            |
| Dispatches subagents                      | D9                  |
| CLI-heavy (binaries or CLIs)              | D5, D7, D10, D11, D22 |
| Has conditional / EARS-style instructions | D14, D15            |
| Cross-skill dependencies                  | D13                 |
| Produces creative/variant outputs         | D19                 |
| References AGENTS.md or external rules    | D20 (already universal) |
| Has scripts that create temp files        | D23                 |
| Multi-step workflows (3+ steps)           | D24                 |
| Handles credentials or API keys           | D25                 |

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
- Name canonicalization does not drift between docs and CLI surfaces.

**Boundary:** D5 checks *name identity and canonical forms*. Discovery-helper
coverage for enum-like options belongs to D22.

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
- WHEN a skill exposes a router CLI, THEN the CLI SHALL disclose deeper
  guidance conditionally (`next-steps`, `step <N>`, `phase <N>`, or equivalent)
  instead of forcing the full manual into context.
- WHEN a skill documents CLI-served guidance, THEN SKILL.md SHALL also
  document the fallback reference path when the CLI is unavailable.

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
- WHEN a skill dispatches subagents, THEN each dispatch prompt SHALL include an explicit **forbidden-actions list** (commands the worker SHALL NOT run).
- WHEN a skill dispatches subagents, THEN each dispatch prompt SHOULD specify **resource limits** (max files to process, max output size, time cap).
- WHEN a dispatch prompt defines scope boundaries, THEN it SHALL explicitly list out-of-scope directories/files, not just in-scope ones.

**Severity:** BLOCKER — prompt references inaccessible context. MAJOR — no output contract; no forbidden-actions list. MINOR — slightly ambiguous scope; no resource limits. NIT — wording tightening.

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
- WHEN a CLI command succeeds, THEN its output SHALL clearly indicate what was done, how many items were processed, and whether any items were skipped.
- WHEN a CLI command partially succeeds, THEN output SHALL distinguish successes from failures (not just report the total count).
- WHEN a CLI command completes, THEN its output SHOULD indicate what the agent should do next (or that no further action is needed).
- Exit code 0 SHALL NOT be used when significant sub-tasks failed silently.

**Severity:** BLOCKER — default output >20 KB, no filter; exit 0 on silent failure. MAJOR — no structured-output flag; no success/failure distinction in partial results. MINOR — slightly >4 KB; no next-steps hint. NIT — decorative TTY elements.

---

### D11: cold-start-readiness

**Source:** Phase 1 — Environment & Build · **Tier:** Deterministic
**Script:** `<skills-file-root>/scripts/cold_start_check.sh`

**Seed checks:**
- Runs in <5 s on first invocation (no compile step).
- No cargo build, npm install, or equivalent on first use.
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
- Scripts SHALL NOT use GNU-specific flags without POSIX fallbacks. Common violations:
  - `sed -i` without backup suffix argument (GNU vs BSD)
  - `grep -P` (Perl regex, not POSIX; use `grep -E` instead)
  - `readlink -f` (GNU-only; use a POSIX-compatible alternative)
  - `mktemp` with GNU-specific template patterns
- WHEN a script targets `#!/usr/bin/env sh`, THEN it SHALL NOT use bash-specific constructs (`[[ ]]`, `$(( ))` with non-POSIX arithmetic, `local` in non-function context, arrays).
- WHEN platform-specific behavior exists, THEN the script SHALL detect the platform and adapt, or document the limitation.

**Severity:** BLOCKER — silent failure on missing dep; GNU-specific flag causes failure on BSD/macOS. MAJOR — dep undocumented; bashism without bash shebang. MINOR — bashism in non-critical path. NIT — shared preamble opportunity.

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
