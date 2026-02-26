# Audit Phases — Detailed Instructions

This document contains the step-by-step procedure for each audit phase. Read
it before starting Phase 1 so you have the full picture, then refer back to
each section as you enter that phase.

---

## Phase 1: Environment & Build

**Goal:** Can an agent actually run this skill's tools on first contact?

This phase catches the issues that block everything else: broken scripts,
missing dependencies, build failures, permission problems. The principle is
simple — **execute first, read second.** Many issues (like CRLF line endings)
are invisible in code but immediately fatal on execution.

### Steps

1. **Map the skill directory tree.** List all files with sizes. Note:
   - Scripts (`.sh`, `.py`, wrapper files without extensions)
   - Binaries (compiled executables in `target/`, `bin/`, etc.)
   - Config files (`.toml`, `.yml`, `.json`)
   - Reference docs (`.md` files in `references/`)
   - Assets (templates, fonts, images)

2. **Run `surface_check.sh`** if available, or perform these checks manually:

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

3. **Execute every script/binary AS-IS.** Don't fix anything first. For each:
   - Run with `--help` or no arguments
   - Record: did it succeed? What was the output? What was the exit code?
   - If it failed, record the exact error message

4. **If a build step is required** (the skill has source code that needs
   compiling):
   - Check if a pre-built binary exists. If not, note it as a finding.
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
| scripts/mpcr (wrapper) | ❌ CRLF shebang | /usr/bin/env: 'sh\r': No such file | GNU sed: `sed -i 's/\r$//'` \| BSD/macOS sed: `sed -i '' 's/\r$//'` |
| scripts/mpcr-src (build) | ✅ after 1m39s | — | Ship pre-built binary |
| mpcr --help | ✅ | — | — |
```

---

## Phase 2: API Surface

**Goal:** Every name in the documentation must resolve in the CLI. Every CLI
command must be reachable from the documentation.

Name mismatches between docs and CLI are the single most common agent failure
mode. An agent reads "Architecture" in the docs, tries
`--role architecture`, and gets an error. This phase catches every instance.

### Steps

1. **Map the full CLI surface.** Run `--help` on the top-level command and
   every subcommand. Build a tree:
   ```
   tool
   ├── subcommand-a [--flag1, --flag2, ...]
   │   ├── sub-sub-a1
   │   └── sub-sub-a2
   └── subcommand-b [--flag1, ...]
   ```

2. **Identify all named enumerations.** These are parameters that accept a
   fixed set of values (roles, phases, modes, scales, statuses). For each:
   - List all values the CLI accepts (from `--help`, error messages, or source)
   - List all values the documentation mentions
   - Cross-reference. Flag mismatches.

   This is the highest-value step in the entire audit. Do it exhaustively.

   ```bash
   # Pattern: try documented name, then try plausible alternatives
   for name in documented-name1 documented-name2 variant1 variant2; do
       result=$(tool subcommand --param "$name" 2>&1 | head -1)
       echo "$name → $result"
   done
   ```

3. **Test every documented command.** Go through SKILL.md and all reference
   docs. For every command shown (including examples, quick-reference blocks,
   and inline code), execute it (substituting real IDs where needed). Record:
   - Does it work?
   - Does the output match what the docs describe?
   - How large is the output (lines, chars)?

4. **Test error quality.** For each command, deliberately provide bad input.
   Evaluate the error message:
   - Is it short and actionable? (GOOD)
   - Does it include valid alternatives? (GOOD)
   - Does it dump a stack backtrace? (BAD — wastes agent tokens)
   - Is the error message misleading? (BAD)

5. **Build the complete name mapping.** Produce a table mapping every
   documented concept name to its CLI representation:

   ```
   | Documented Name | CLI Representation | Documented? | Works? |
   |----------------|-------------------|-------------|--------|
   | Architecture | architecture-critic | ❌ | ✅ |
   | INGESTION | INGESTION | ✅ | ✅ |
   ```

### What to record

- The full CLI surface tree
- The name mapping table (this goes directly into the report appendix)
- Every command that fails with its error message
- Error quality assessment (short summary)

---

## Phase 3: Workflow Simulation

**Goal:** Walk through the skill's workflow exactly as an agent would,
executing every step, and record what happens.

This is the most important phase. Phases 1 and 2 test individual components;
this tests the *experience* of following the instructions as a whole.

### Steps

1. **Create a test project** appropriate to the skill's domain (see the
   "Test project creation" section in SKILL.md for guidance).

2. **Initialize version control** if the skill works with diffs or branches:
   ```bash
   cd audit-workspace && git init
   git config user.email "audit@test.com" && git config user.name "Auditor"
   # Create initial commit, then a feature branch with changes
   ```

3. **Follow the documented workflow step-by-step.** Start from the very first
   instruction in the skill's SKILL.md. At each step:

   a. Execute the command or action exactly as documented.
   b. Record the output (or a summary if it's large).
   c. Note any ambiguity: "What should I do next?" moments.
   d. Note any surprise: output that doesn't match expectations.
   e. Measure the output size (lines/chars) for context analysis later.

4. **Exercise the full lifecycle.** Don't stop at the first success. Complete
   the entire workflow from start to finish, including:
   - Registration/setup
   - All intermediate steps
   - Finalization/cleanup
   - Output verification

5. **Test at least one error recovery path.** Deliberately cause a step to
   fail midway and see if the skill's documentation tells you how to recover.

6. **If the skill has multiple modes** (e.g., reviewer / applicator /
   full-cycle), test at least the primary mode end-to-end and spot-check
   the others.

### What to record

A step-by-step narrative:
```
Step 1: Ran `tool register --target-ref feature/x`
  Output: {reviewer_id: "abc123", session_id: "def456"}
  Status: ✅ 
  Notes: Output is clean JSON, easy to parse.

Step 2: Ran `tool protocol orchestrator`
  Output: 134 lines, 8246 chars
  Status: ✅ but MAJOR context concern
  Notes: This dumps the entire orchestration protocol into context.
         Agent now has ~12,000 chars of instructions before reading any code.
```

### Ambiguity scoring

At each step, rate the clarity of "what to do next" on a 1-3 scale:
- **1 (Clear):** The documentation explicitly says what command to run next.
- **2 (Inferrable):** A capable agent can figure it out, but it's not explicit.
- **3 (Ambiguous):** An agent would likely guess wrong or need to ask.

Count your 3s. More than 2 in a workflow is a MAJOR finding.

---

## Phase 4: Context & Token Analysis

**Goal:** Quantify every document's token cost and identify duplication.

Agent context windows are finite and expensive. Every unnecessary token in a
skill's instructions is a token that can't be used for the actual task.

### Steps

1. **Measure every document.** For each file in the skill directory:
   ```bash
   wc -lc <file>  # lines and characters
   ```
   Estimate tokens as `chars / 4` (rough approximation for English text).

2. **Measure every protocol/template output** if the skill has a CLI that
   serves instructions (like `mpcr protocol`):
   ```bash
   tool protocol subcommand 2>&1 | wc -lc
   ```

3. **Build the context budget table:**

   | Component | Chars | Est. Tokens | Loaded When |
   |-----------|-------|-------------|-------------|
   | SKILL.md | 18,029 | ~4,500 | Always (skill trigger) |
   | protocol orchestrator | 8,246 | ~2,060 | Orchestrator start |
   | ... | ... | ... | ... |

4. **Identify duplication.** Read each pair of documents and flag content
   that appears in multiple places. Common duplication patterns:
   - Workflow steps repeated in SKILL.md AND protocol outputs
   - Rules repeated in SKILL.md AND reference documents
   - Quick-reference sections that duplicate what the CLI provides

   For each duplication, note:
   - What content is duplicated
   - Which documents contain it
   - Estimated wasted tokens

5. **Calculate total context at peak.** What's the maximum context an
   orchestrator agent would hold simultaneously? This is:
   ```
   SKILL.md + protocol outputs loaded so far + subagent results pending
   ```

6. **Propose a reduction target.** Based on the duplication analysis, estimate
   how much context could be cut. A good target is 40-50% reduction from peak.
   List specific cuts:
   - "Remove workflow steps from SKILL.md (defer to protocol output): -2,000 tokens"
   - "Deduplicate concurrency cap across 4 documents: -400 tokens"

### What to record

- The full context budget table
- Duplication map with token estimates
- Peak context calculation
- Proposed reduction target with specific line items

---

## Phase 5: Output Quality

**Goal:** Are the skill's templates, dispatch prompts, and generated outputs
thorough, consistent, and tailored to their purpose?

### Steps

1. **Inventory all output artifacts.** These include:
   - Dispatch/worker prompts (for multi-agent skills)
   - Report templates
   - Generated files (if the skill produces documents, code, configs)
   - Protocol guidance outputs

2. **Compare for consistency.** If the skill has multiple variants of the
   same output type (e.g., dispatch prompts for different roles), compare:

   a. **Depth consistency:** Measure the size of each variant. Flag any that
      are less than 60% of the median size — they're likely shallow.

   b. **Structural consistency:** Do all variants follow the same template?
      Do they all have the same sections? Flag missing sections.

   c. **Domain tailoring:** Does each variant have content specific to its
      domain, or is it mostly generic boilerplate? A dispatch prompt that's
      90% shared text and 10% domain-specific is probably too generic.

3. **Fill in one template with test data.** Take the skill's primary output
   template (report template, dispatch prompt, etc.) and fill it in using
   data from your Phase 3 workflow simulation. Evaluate:
   - Are all fields clear and unambiguous?
   - Are there fields an agent would struggle to fill?
   - Does the filled template meet the quality bar described in the docs?

4. **Check for anti-laziness guardrails.** Does the skill include mechanisms
   to prevent shallow or generic output? Examples:
   - Minimum counts (e.g., "at least 2 theorems per domain")
   - Specificity requirements (e.g., "must reference file:line")
   - Explicit anti-patterns (e.g., "'the code works' is NOT a valid proof")

   If these are missing, note it — agents tend toward shallow output without
   explicit depth requirements.

### What to record

- Size comparison table across variants
- Structural comparison (sections present/absent per variant)
- Domain-tailoring assessment
- Template fill-in evaluation
- Anti-laziness guardrail inventory

---

## Finding accumulation

Throughout all phases, write findings to a running report file in your
audit workspace as you discover them. Use this format:

```markdown
### [ID]: [Title]
- **Phase:** [1-5]
- **Severity:** BLOCKER | MAJOR | MINOR | NIT
- **Anchor:** [file:line or command]
- **Evidence:** [exact error, measurement, or output]
- **Impact:** [what happens to an agent that hits this]
- **Fix:** [specific recommendation]
```

Number findings sequentially: C1, C2 for BLOCKERs; M1, M2 for MAJORs; m1, m2
for MINORs; n1, n2 for NITs.

After all phases, reorganize and deduplicate before writing the final report.

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
5. Phase 5 size comparison only (skip template fill-in)
