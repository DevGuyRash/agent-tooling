# Audit Phases — Core (Phases 1–3)

This document contains the step-by-step procedure for the core audit phases
(1–3). Read it before starting Phase 1 so you have the full picture, then
refer back to each section as you enter that phase.

The agent is the auditor. Helper scripts accelerate deterministic evidence
collection, but they do not replace the running report, the workflow
simulation, or the final judgment. Start writing findings before Phase 1 and
keep the report open while you work.

## Table of contents

- [Phase 1: Environment & Build](#phase-1-environment--build)
- [Phase 2: API Surface](#phase-2-api-surface)
- [Phase 3: Workflow Simulation](#phase-3-workflow-simulation)
- [Finding accumulation](#finding-accumulation)

---

## Phase 1: Environment & Build

**Goal:** Can an agent actually run this skill's tools on first contact?

This phase catches the issues that block everything else: broken scripts,
missing dependencies, build failures, permission problems. The principle is
simple — **execute first, read second.** Many issues (like CRLF line endings)
are invisible in code but immediately fatal on execution.

Before moving on, ask:

- Which failures actually block a first-run agent?
- Which results came from scripts, and which needed manual inspection?
- What should enter the report immediately as BLOCKER, MAJOR, MINOR, or NIT?

### Steps

1. **Map the skill directory tree.** You SHALL list all files with sizes. Note:
   - Scripts (`.sh`, `.py`, wrapper files without extensions)
   - Binaries (compiled executables in `target/`, `bin/`, etc.)
   - Config files (`.toml`, `.yml`, `.json`)
   - Reference docs (`.md` files in `references/`)
   - Assets (templates, fonts, images)

2. **Run `surface_check.sh`** if available, or perform these checks manually.
   Treat script output as evidence, not as the whole conclusion:

   a. **CRLF detection.** Check every text file for `\r`:
      ```bash
      find <skill-dir> -type f \( -name '*.sh' -o -name '*.rs' -o -name '*.py' \
        -o -name '*.toml' -o -name '*.yml' -o -name '*.md' \) \
        -exec sh -c 'tr -d "\r" < "$1" | cmp -s - "$1" || echo "$1"' _ {} \;
      ```
      CRLF in shell scripts is a BLOCKER (shebang breaks). In other files it's
      a MINOR (cosmetic but signals sloppy hygiene).

   b. **Shebang validation.** For every script, check that the shebang is
      correct and the file is executable:
      ```bash
      find <skill-dir> -type f \( -name '*.sh' -o -name '*.py' \) \
        -exec head -1 {} +
      ```

   c. **Permission check.** Scripts should have execute permission:
      ```bash
      find <skill-dir> -type f -name '*.sh' ! -perm -u+x
      ```

3. **Execute every script/binary AS-IS.** You SHALL NOT fix anything first. For each:
   - You SHALL run with `--help` or no arguments
   - You SHALL record: did it succeed? What was the output? What was the exit code?
   - If it failed, record the exact error message

4. **If a build step is required** (the skill has source code that needs
   compiling):
   - You SHALL check if a pre-built binary exists. If not, note it as a finding.
   - Attempt the build from scratch. Record:
     - What dependencies are needed? Are they available in the environment?
     - How long does the build take?
     - Does the build succeed?
   - After building, re-run the binary with `--help`.

5. **If the skill references companion skills** (e.g., code-review references
   rust-development's scaffold), test those integration points:
   - Can the companion's scripts be found and executed?
   - Do the outputs of one skill feed correctly into the other?

### What to record

For each script/binary/build step:
```
| Item | Status | Error (if failed) | Fix |
|------|--------|--------------------|-----|
| scripts/mpcr (wrapper) | ❌ CRLF shebang | /usr/bin/env: 'sh\r': No such file | GNU sed: `sed -i 's/\r$//'` or BSD/macOS sed: `sed -i '' 's/\r$//'` |
| scripts/mpcr-src (build) | ✅ after 1m39s | — | Ship pre-built binary |
| mpcr --help | ✅ | — | — |
```

### Domain scripts

The auditor SHOULD run the following domain scripts during this phase when they
save time or increase confidence:

- D1 (`<skills-file-root>/scripts/surface_check.sh`)
- D2 (`<skills-file-root>/scripts/frontmatter_check.sh`)
- D3 (`<skills-file-root>/scripts/description_check.sh`)
- D4 (`<skills-file-root>/scripts/path_token_check.sh`)
- D11 (`<skills-file-root>/scripts/cold_start_check.sh`)
- D12 (`<skills-file-root>/scripts/dependency_check.sh`)

WHEN a script is not present or does not cover the observed issue, THEN the
auditor SHALL perform equivalent checks manually and record the gap as part of
the finding.

---

## Phase 2: API Surface

**Goal:** Every name in the documentation must resolve in the CLI. Every CLI
command must be reachable from the documentation.

Name mismatches between docs and CLI are the single most common agent failure
mode. An agent reads "Architecture" in the docs, tries
`--role architecture`, and gets an error. This phase catches every instance.

Before moving on, ask:

- Can a fresh agent discover the right names without guessing?
- Do the docs and runtime agree on what exists?
- Which mismatches are merely noisy versus workflow-breaking?

### Steps

1. **Map the full CLI surface.** You SHALL run `--help` on the top-level command and
   every subcommand. Build a tree:
   ```
   tool
   ├── subcommand-a [--flag1, --flag2, ...]
   │   ├── sub-sub-a1
   │   └── sub-sub-a2
   └── subcommand-b [--flag1, ...]
   ```

2. **Identify all named enumerations.** You SHALL identify these as parameters that accept a
   fixed set of values (roles, phases, modes, scales, statuses). For each:
   - List all values the CLI accepts (from `--help`, error messages, or source)
   - List all values the documentation mentions
   - You SHALL cross-reference and flag mismatches.

   This is the highest-value step in the entire audit. Do it exhaustively.

   ```bash
   # Example pattern (pseudocode): substitute your real tool/subcommand names.
   # Do not run this block literally as `tool ...`.
   for name in documented-name1 documented-name2 variant1 variant2; do
       result=$(tool subcommand --param "$name" 2>&1 | head -1)
       echo "$name → $result"
   done
   ```

3. **Test every documented command.** You SHALL go through SKILL.md and all reference
   docs. For every *runnable* command shown (including quick-reference blocks
   and inline code), execute it (substituting real IDs where needed).
   IF a command uses generic placeholders (for example `tool ...`),
   THEN treat it as a pattern unless it is concretized for the skill under
   audit. Record:
   - Does it work?
   - Does the output match what the docs describe?
   - How large is the output (lines, chars)?

4. **Run staleness drift checks.** You SHALL execute:
   ```bash
   <skills-file-root>/scripts/staleness_check.sh <skill-directory> [--cli <bin>] [--format text|json]
   ```
   Then inspect script results and surrounding prose claims to determine:
   - Which examples are still runnable as documented
   - Which examples reference missing scripts/flags/subcommands
   - Which command-shaped inline/fenced examples were extracted after
     multiline normalization
   - Which examples were validated via direct execution vs help fallback
   - Which prose claims drift from actual runtime transcript
   - Which examples appear runnable but rely on hidden substitutions/setup

5. **Test error quality.** You SHALL, for each command, deliberately provide bad input.
   Evaluate the error message:
   - Is it short and actionable? (GOOD)
   - Does it include valid alternatives? (GOOD)
   - Does it dump a stack backtrace? (BAD — wastes agent tokens)
   - Is the error message misleading? (BAD)

6. **Build the complete name mapping.** You SHALL produce a table mapping every
   documented concept name to its CLI representation:

   ```
   | Documented Name | CLI Representation | Documented? | Works? |
   |----------------|-------------------|-------------|--------|
   | Architecture | architecture-critic | ❌ | ✅ |
   | Correctness | correctness | ✅ | ✅ |
   ```

### What to record

- The full CLI tree
- The complete name mapping table
- Every command tested with result (✅/❌) and output size
- Staleness drift matrix (example → observed runtime status)
- Error quality evaluation for each command

### Domain scripts

The auditor SHOULD run the following domain scripts during this phase when they
accelerate evidence gathering. CLI-dependent scripts require a CLI binary; D21
and D22 SHOULD still run without `--cli` to validate local script-path and
discoverability examples:

- D5 (`<skills-file-root>/scripts/name_consistency_check.sh`)
- D7 (`<skills-file-root>/scripts/error_quality_check.sh`)
- D10 (`<skills-file-root>/scripts/output_size_check.sh`)
- D21 (`<skills-file-root>/scripts/staleness_check.sh`)
- D22 (`<skills-file-root>/scripts/discoverability_check.sh`)

WHEN no CLI binary is available, THEN the auditor SHALL skip CLI-dependent
checks (D5, D7, D10, D22), continue the agent audit with manual evidence, and
note the reason in the report.

---

## Phase 3: Workflow Simulation

**Goal:** Walk through the skill's primary workflow as an agent would, end to
end, recording every friction point.

This is where you stop testing individual commands and start testing the
*experience*. You're simulating what an agent goes through when it triggers
this skill.

Before moving on, ask:

- Where did the workflow become ambiguous or brittle?
- Which parts required hidden prior knowledge?
- Which friction points deserve immediate findings instead of end-of-phase notes?

### Steps

1. **Identify the primary workflow.** You SHALL read SKILL.md and find the main
   sequence of steps an agent follows. This is usually a numbered list or
   a flowchart. Write it out as a linear sequence.

2. **Execute each step in order.** You SHALL follow each step:
   - What does the documentation tell you to do?
   - What command(s) do you run?
   - What output do you get?
   - What does the documentation tell you to do with that output?
   - Is the next step clear, or do you have to guess?

3. **Track handoff clarity.** You SHALL, at each step boundary, rate the clarity of
   "what to do next" on a 1-3 scale:
   - **1 (Clear):** The documentation explicitly says what command to run next.
   - **2 (Inferrable):** A capable agent can figure it out, but it's not explicit.
   - **3 (Ambiguous):** An agent would likely guess wrong or need to ask.

   Count your 3s. More than 2 in a workflow is a MAJOR finding.

4. **Write findings immediately.** After each simulated step, update the
   running report while the transcript, outputs, and confusion points are
   still fresh. Do not defer workflow findings to final synthesis.

### Domain scripts

The auditor SHALL evaluate D6 (command isolation) during workflow simulation.
WHEN the workflow passes state between commands via environment variables,
THEN the auditor SHALL check for env-var-across-command patterns and flag
them as findings.

---

## Finding accumulation

Throughout all phases, write findings to a running report file under
`~/.local/reports/skill-auditor/<skill-name>/<YYYY-MM-DD>/` as you discover
them. The report is the audit product; helper
script output is supporting evidence. You SHALL use the canonical field schema
from `<skills-file-root>/references/report-template.md` ("Phase 1 Findings" example). You MAY use
this shorthand format while collecting findings:

```markdown
### [ID]: [Title]
- **Phase:** [1-5]
- **Severity:** BLOCKER | MAJOR | MINOR | NIT
- **Confidence:** HIGH [H] | MEDIUM [M] | LOW [L] — <evidence basis>
- **Anchor:** [file:line or command]
- **Evidence:** [exact error, measurement, or output]
- **Impact:** [what happens to an agent that hits this]
- **Fix:** [specific recommendation]
```

Number findings sequentially: C1, C2 for BLOCKERs; M1, M2 for MAJORs; m1, m2
for MINORs; n1, n2 for NITs.

After all phases, reorganize and deduplicate before writing the final report.
Do not mistake a clean helper-script run for a clean audit; the report still
needs agent synthesis, prioritization, and verdict reasoning.
