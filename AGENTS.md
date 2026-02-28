# Repo-wide agent notes

This file contains cross-cutting constraints that apply regardless of language or skill.
Language/toolchain-specific workflows live in the corresponding skill `SKILL.md` files under `skills/`.

Skills in this repo follow the [Open Agent Skills standard](https://agentskills.io/specification).
Skills authored to this standard are portable across Claude, Codex, GitHub Copilot,
Cursor, OpenCode, and 20+ other platforms without modification — so following the
conventions here isn't just local hygiene, it's cross-platform compatibility.

---

## ⚠️ Command Isolation: Environment Variables Do NOT Persist Across Commands

**Critical for agents and subagents**: Each `exec_command` / shell invocation runs in a **completely isolated** process. Environment variables set via `export`, `cd` directory changes, shell aliases, and any other process-level state are **lost** between commands.

### What does NOT work

```bash
# Command 1
export MY_SESSION_ID=abc123
cd /some/project
```
```bash
# Command 2 — these are NOT set; directory is reset
echo $MY_SESSION_ID   # empty
pwd                    # not /some/project
```

### What works instead

**Option A (recommended): pass values as CLI flags**:
```bash
tool update --session-id abc123 --status IN_PROGRESS
```

**Option B: capture output and re-pass as flags**:

Some CLIs offer a `--print-env` flag that outputs the values you need for
subsequent commands. Capture them in one command, then pass as flags:
```bash
# mpcr example: register prints IDs you'll need later
mpcr reviewer register --target-ref main --print-env
# Output: MPCR_REVIEWER_ID=deadbeef MPCR_SESSION_ID=sess0001
# Use those values as explicit flags in the next command:
mpcr reviewer update --reviewer-id deadbeef --session-id sess0001 --status IN_PROGRESS
```

**Option C: chain commands in a single shell invocation**:
```bash
export MY_SESSION_ID=abc123 && cd /some/project && tool update --use-env
```

This applies to any CLI that offers `--use-env` or environment-based
configuration (e.g., `mpcr`'s `MPCR_*` variables). Those patterns are
designed for shell scripts and CI pipelines where the entire pipeline runs
in one shell session. When used by agents — where each command is a separate
process — environment-based configuration provides no benefit.

**Always prefer explicit CLI flags over environment variables when running
from agents.**

---

## Skill authoring: `<skills-file-root>`

When writing or editing a skill, use `<skills-file-root>` as the path prefix for all references to files within the skill directory (scripts, references, assets). It resolves to the directory containing the skill's `SKILL.md`.

---

## Skill authoring: frontmatter and naming

Every skill's `SKILL.md` starts with YAML frontmatter. The `name` and
`description` fields are required by the spec and have strict constraints.

### Name field

The `name` must match the parent directory name and follow these rules:

- Lowercase alphanumeric characters and hyphens only (`a-z`, `0-9`, `-`)
- Max 64 characters
- Must not start or end with `-`
- Must not contain consecutive hyphens (`--`)

Valid: `code-review`, `pdf-processing`, `rust-development`
Invalid: `Code-Review` (uppercase), `-pdf` (leading hyphen), `pdf--tools` (consecutive hyphens)

### Description field

The description is the single most important line in a skill. It's the
primary mechanism every platform uses to decide whether to activate the
skill — agents see descriptions for all available skills at startup and
match against the user's request.

Rules from the spec:
- Max 1024 characters
- Must describe both *what* the skill does and *when* to use it
- Should include specific keywords that users are likely to say

A good description covers trigger conditions explicitly:

```yaml
description: >-
  Extract text and tables from PDF files, fill PDF forms, and merge
  multiple PDFs. Use when working with PDF documents or when the user
  mentions PDFs, forms, or document extraction.
```

A poor description forces the agent to guess:

```yaml
description: Helps with PDFs.
```

Test your description by imagining 5-10 realistic user prompts that should
trigger the skill and 5-10 that shouldn't. If the description doesn't
clearly distinguish them, rewrite it.

---

## Skill authoring: file hygiene

All text files shipped in a skill — scripts, source, configs, protocol data,
references, templates — SHALL use LF (`\n`) line endings, never CRLF (`\r\n`).

CRLF in a shell script is a silent blocker: the shebang becomes
`#!/usr/bin/env sh\r` and Linux resolves that as a missing binary. An agent
encountering this wastes its entire turn on a confusing error. The same
problem affects Python scripts, TOML configs loaded at runtime, and any file
`cat`-piped into another command.

Before committing any skill file:

```bash
# Detect CRLF in the skill directory
find <skill-dir> -type f \( -name '*.sh' -o -name '*.py' -o -name '*.rs' \
  -o -name '*.toml' -o -name '*.yml' -o -name '*.md' \) \
  -exec grep -Plc '\r' {} + 2>/dev/null
```

If any files match, fix them: `sed -i 's/\r$//' <file>`. Enforce this in CI
or use `.gitattributes` with `* text=auto eol=lf`.

Shell scripts additionally SHALL have executable permission (`chmod +x`) and a
valid shebang (e.g., `#!/usr/bin/env sh`).

---

## Skill authoring: name consistency between docs and CLI

Every name that appears in a skill's documentation — role names, phase names,
mode names, parameter values — SHALL be the exact string the CLI or API
accepts. If the CLI accepts `architecture-critic`, the docs say
`architecture-critic`, not `Architecture` or `architecture`.

Name mismatches between documentation and implementation are the single most
common agent failure mode. An agent reads a domain table listing
"Architecture," tries `--role architecture`, gets an error, tries
`--role Architecture`, gets another error, and either fabricates a workaround
(breaking protocol consistency) or enters a retry loop burning tokens.

Rules:

1. **One canonical form.** Pick one representation for each name and use it
   everywhere: SKILL.md, reference docs, CLI `--help`, error messages, and
   protocol outputs. If the CLI normalizes input (e.g., lowercases and
   replaces hyphens with underscores), document the canonical form the user
   should type, not the internal form.

2. **Discovery command.** If a CLI accepts a set of named values, it SHALL
   offer a way to list them. For example, `tool dispatch --list` or
   `tool --help` showing valid values. An agent that hits an invalid name
   should be one command away from finding the valid names — not searching
   through docs.

3. **Mapping tables.** When documentation uses a human-friendly name
   (e.g., "Architecture") that differs from the CLI slug
   (e.g., `architecture-critic`), the documentation SHALL include an explicit
   mapping table showing both forms. Don't force the agent to infer the mapping.

4. **Test every name.** Before shipping a skill, execute every named value
   mentioned in the docs against the CLI. This catches drift between docs and
   implementation that's invisible during code review.

---

## Skill authoring: error messages designed for agents

When a skill includes a CLI or script that agents will invoke, error output
SHALL be short, actionable, and context-efficient. Agents pay for every
character of error output — it consumes their working context.

Rules:

1. **No stack backtraces in normal errors.** A backtrace for "unknown role
   name" is never useful to an agent. Set `RUST_BACKTRACE=0` or equivalent
   in wrapper scripts, or structure error handling to emit clean messages.

2. **Include valid alternatives in error messages.** When input doesn't match
   a known value, the error should say what the valid values are:

   ```bash
   error: unknown role "architecture"
   valid roles: architecture-critic, contract-guardian, ...
   ```
   This turns a dead-end error into a self-correcting one.

3. **Keep errors to 1-3 lines.** An error message beyond 3 lines is noise.
   If extra detail is needed, put it behind a `--verbose` flag.

4. **Consistent format.** Errors from a skill's CLI should follow a uniform
   pattern so agents can parse them mechanically:

   ```bash
   error: <what went wrong>
   hint: <what to do instead>
   ```

---

## Skill authoring: progressive disclosure and context budgets

Agent context windows are finite and expensive. Every token of instruction
that an agent holds is a token that can't be used for the actual task. Skills
SHALL be designed so the agent only loads the instructions it needs for the
current step, not everything up front.

### The three-layer loading model

Skills follow a three-level progressive disclosure system. Each layer loads
at a different time and serves a different purpose.

| Layer                                                        | Loaded when              | Target size                                | Purpose                                                               |
| ------------------------------------------------------------ | ------------------------ | ------------------------------------------ | --------------------------------------------------------------------- |
| **Metadata** (name + description in frontmatter)             | Always in context        | ~100 words                                 | Trigger detection — does this skill apply?                            |
| **SKILL.md body**                                            | When skill triggers      | <500 lines                                 | Routing: what workflow am I in? What do I read next?                  |
| **Bundled resources** (`references/`, `scripts/`, `assets/`) | On demand, one at a time | Unlimited total; <300 lines per file ideal | Detail: full procedures, rubrics, templates, domain-specific guidance |

The critical principle: **the agent reads deeper only when needed.** SKILL.md
tells the agent which reference file to read for its current situation. The
agent loads that one file, follows its instructions, and never touches the
other references.

### SKILL.md is a router, not a manual

SKILL.md answers three questions and stops:

1. "What is this skill and when does it trigger?"
2. "What workflow am I in?" (mode selection based on user input)
3. "What do I read next?" (pointer to the right reference file or script)

SKILL.md should NOT contain detailed procedures, full rubrics, or extended
specifications. Those belong in `references/` files. When SKILL.md tries to
be both router and manual, it bloats past 500 lines and the agent pays the
full token cost every time, even when most of the content is irrelevant to
the current task.

### Reference files are the primary disclosure mechanism

The `references/` directory is how most skills deliver just-in-time
instructions. There are three proven patterns for organizing them:

**Pattern 1: Conditional loading with a reference index.**
SKILL.md contains a table mapping situations to files. The agent reads only
the row that matches.

```markdown
## Reference index

You SHALL load only the reference needed for the current task.

| File                       | When to read                       |
| -------------------------- | ---------------------------------- |
| `references/guidelines.md` | Phase 1 of any workflow            |
| `references/migration.md`  | Converting a non-Rust tool to Rust |
| `references/monorepo.md`   | Working in a Rust workspace        |
```

**Pattern 2: Domain-variant organization.**
When a skill supports multiple domains or frameworks, split references by
variant. The agent loads only the variant it needs.

```bash
cloud-deploy/
├── SKILL.md          (workflow selection + routing)
└── references/
    ├── aws.md        (loaded only for AWS tasks)
    ├── gcp.md        (loaded only for GCP tasks)
    └── azure.md      (loaded only for Azure tasks)
```

**Pattern 3: Inline links at point of relevance.**
SKILL.md contains reference links right where the agent needs them, woven
into the workflow narrative. Good for smaller skills.

```markdown
## Output and clipboard policy

For low-latency expansions, prefer `print_only` when the replacement
payload is already emitted by script output.

Read: [references/clipboard-latency.md](references/clipboard-latency.md)
```

All three patterns achieve the same goal: the agent loads one focused
reference at a time instead of everything at once.

### CLI-served protocols (advanced pattern)

Some skills include a CLI that serves instructions dynamically — for example,
`tool protocol orchestrator` outputs orchestration guidance, and
`tool protocol dispatch --role X` outputs a role-specific prompt. This is
a powerful progressive disclosure mechanism because the CLI can tailor
output to the current phase or role.

When a skill has this kind of CLI, the `references/` files serve as fallback
for when the CLI is unavailable (not built, wrong platform, missing
dependency). The SKILL.md should say:

```markdown
You SHALL run `tool protocol orchestrator` for guidance.
IF the CLI is unavailable, read `references/orchestrator-fallback.md` instead.
```

The CLI output and the fallback reference SHALL contain the same information.
They are two delivery mechanisms for one source of truth, not two documents
that drift apart over time. Ideally the CLI embeds the reference content
directly (e.g., from TOML or markdown files compiled into the binary) so
they are literally the same text.

### Each fact lives in exactly one place

The most insidious context problem is duplication: the same rule, procedure,
or constraint described in SKILL.md AND a reference file AND a CLI output.
The agent pays for all three copies, and when they inevitably drift apart,
the agent gets conflicting instructions.

Common duplication to watch for:

- **Workflow steps** narrated in SKILL.md and repeated in detail in a
  reference file. SKILL.md should give a 1-line summary and point to the
  reference; the reference has the detail.
- **Rules and constraints** (concurrency caps, forbidden actions, cleanup
  requirements) stated in SKILL.md and again in reference docs. State the
  rule once; the other location says "see X."
- **Command quick-references** in SKILL.md that reproduce what `--help` or
  a script already provides. If the agent can run a command to get the
  information, SKILL.md doesn't need to list it.

When in doubt, ask: "If I change this fact, how many files do I need to
edit?" If the answer is more than one, there's duplication.

### Reference file sizing and depth

SKILL.md can point to as many reference files as needed — that's the whole
point of the reference index pattern. The constraint is on *nesting*: a
reference file should not point to another reference file. If Reference A
tells the agent to read Reference B, which tells it to read Reference C,
the agent is in a context spiral — accumulating instructions without making
progress. All references should be reachable directly from SKILL.md, not
through other references. If a reference needs information from another
file, inline it or restructure.

For reference files over 300 lines, include a table of contents at the top
so the agent can jump to the relevant section. In practice, the most
effective reference files across existing skills are 50-150 lines — focused
enough to load quickly, detailed enough to be self-contained for their topic.

If a reference file exceeds 300 lines, consider splitting it into two files
with separate conditional triggers from SKILL.md, so the agent only loads
the half it needs.

### Measuring your context budget

Before shipping a skill, measure what the agent actually loads during a
typical invocation:

```bash
# Measure every document in the skill
find <skill-dir> -name '*.md' -exec wc -c {} + | sort -n
# Estimate tokens: chars / 4
```

The key metric is **peak context** — the maximum number of skill-instruction
tokens the agent holds at any single point during the workflow. This is
NOT the sum of all files (the agent doesn't load them all at once); it's
SKILL.md plus whichever reference file(s) the agent has loaded at the
busiest point.

Good targets:
- SKILL.md alone: under ~4,000 tokens (~16,000 chars)
- SKILL.md + one reference: under ~8,000 tokens
- Peak context including all loaded references: under ~12,000 tokens

These leave the majority of the agent's context window for the actual task:
code, diffs, user instructions, and tool output.

---

## Skill authoring: subagent dispatch prompt design

When a skill dispatches work to subagents, the dispatch prompt is the single
most important artifact. A worker subagent has NO access to the skill's
SKILL.md, reference docs, or conversation history — the dispatch prompt IS
their entire instruction set.

### Self-containment

The dispatch prompt SHALL contain everything the worker needs:
- What to do (task description)
- What to work on (file list, scope boundaries)
- What NOT to do (forbidden actions, scope limits)
- What to return (output format template)
- How to identify themselves (IDs, session info)

If the prompt says "follow the reviewer protocol" without including the
protocol, the worker is stuck.

### Scope containment

The dispatch prompt SHALL explicitly list forbidden actions. Workers that can
accidentally run orchestrator-level commands (registration, spawning children,
finalization) will corrupt session state.

### Output contracts

The dispatch prompt SHALL include an explicit output template — not prose
describing what to return, but a fill-in-the-blank structure. This ensures
the orchestrator can reliably parse and synthesize results from multiple
workers.

### Cross-role consistency

When a skill has multiple dispatch roles, all roles SHALL share the same
structural template (same sections in the same order) with domain-specific
content swapped in. Roles with less than 60% of the median prompt depth are
likely too shallow to produce useful output.

---

## Skill authoring: output size discipline

When a skill's CLI or script produces output that an agent will consume,
that output SHALL be sized for agent context, not human terminals.

Rules:

1. **Default to compact output.** JSON on one line, not pretty-printed.
   Summaries, not full dumps. An agent can request verbose output with a flag
   if needed.

2. **Offer filtering and pagination.** If a command can return unbounded data
   (e.g., all session reports with full contents), provide flags to limit
   output: `--summary-only`, `--max-items N`, `--fields id,status`.

3. **Separate metadata from content.** If a command returns both structural
   metadata (IDs, statuses) and large content (full report text), let the
   agent request them separately rather than dumping everything at once.

4. **Measure your outputs.** Run every command your skill documents and
   measure the output size. If any single command produces more than 5,000
   characters, consider whether the agent actually needs all of it, and add
   a compact mode if not.

---

## Skill authoring: cold-start readiness

A skill SHALL be usable without requiring the agent to install a toolchain,
compile source code, or download large dependencies on first run. The first
invocation should work in under 5 seconds.

If a skill includes compiled tools (Rust binaries, Go binaries, etc.):
- Ship a pre-built binary for the target platform alongside the source.
- The wrapper script should prefer the pre-built binary and fall back to
  building from source only if the binary is missing or outdated.

If a skill depends on runtime tools (Python packages, npm modules):
- Document the dependencies in the SKILL.md `compatibility` field.
- Prefer vendored or self-contained scripts over tools requiring `pip install`
  or `npm install`.
- If installation is unavoidable, make it automatic and silent (the agent
  should not need to know it's happening).

An agent that spends 3 minutes installing Rust and building a binary is an
agent that's not doing the user's task.

### Script self-containment

Scripts in `scripts/` SHALL be self-contained or clearly document their
dependencies. When an agent runs a script, the script's source code never
enters the context window — only its output does. This makes scripts
significantly more token-efficient than having the agent write equivalent
code inline. A 200-line Python script that produces 5 lines of output
costs 5 lines of context, not 200. Lean into this: prefer bundled scripts
over inline instructions whenever the task involves deterministic logic,
data transformation, or validation that would otherwise consume agent
context to reason through.

---

## Skill authoring: integration testing across skills

When a skill references or depends on another skill's outputs (e.g., a code
review skill that uses a Rust skill's scaffold to set up lint configs), the
integration point SHALL be tested end-to-end.

Common failure: Skill A scaffolds configuration files. Skill B's verification
step runs lint checks. The scaffolded config is stricter than the scaffolded
test files, so verification fails immediately after setup. Neither skill is
broken in isolation — the failure only appears at the integration boundary.

Before shipping interconnected skills:
1. Run Skill A's setup.
2. Run Skill B's verification on Skill A's output.
3. Confirm zero failures without manual intervention.

---

## Skills debugging: error accumulation log

Whenever you or any subagent encounter ANY issue while following, reading,
interpreting, or executing a skill's instructions — document it. Every error,
misinterpretation, ambiguity, or unexpected outcome gets logged. Over time
these logs reveal systemic problems that no single run would surface.

### What to log

Every skill friction point: commands that fail, instructions that are
ambiguous, names that don't resolve, outputs that don't match what the docs
describe, files that are missing, build steps that break, reference docs
that contradict SKILL.md, dispatch prompts that lack context, or anything
where the skill told you to do X and the outcome was not X.

### How to write entries

Focus on the **what** and **why**, not the fix. You are a field reporter,
not a patch author. Each entry records what you tried, what the skill told
you to do, what actually happened, and how you interpreted the instructions.

**Good entry:**
> Tried to run `mpcr protocol dispatch --role architecture` as specified by
> SKILL.md line 160: _"Use `mpcr protocol dispatch --role <ROLE>` to get the
> domain-specific prompt."_ The domain table on line 123 lists "Architecture"
> as a domain name. Outcome: `error: unknown dispatch role: architecture`
> with a 15-line stack backtrace. I interpreted "Architecture" in the domain
> table as the role name to pass to `--role`. The actual CLI slug is
> `architecture-critic`, which is not documented anywhere in SKILL.md.

**Bad entry:**
> The dispatch role name is wrong. It should be `architecture-critic` instead
> of `architecture`. Fix line 123 to show the correct slug.

The bad entry jumps to a fix. The good entry captures the chain of
interpretation — what the agent read, how it reasoned, what it tried, and
what broke. This is what makes the log useful for diagnosing skill design
problems rather than just patching individual bugs.

### Where to write

Create one error file per skill at the start of a top-level task invocation.
If the same skill produces multiple errors during that task, append new
entries to the same file. "Top-level task" means one user request that may
span many agent turns and subagent invocations — not each individual command.

File path:

```
<tmp>/<yyyy-mm-dd>/<HH-MM-SS>_<skill-name>_errors.md
```

Where `<tmp>` resolves per platform:

| Platform      | Path                                                                                |
| ------------- | ----------------------------------------------------------------------------------- |
| Linux / macOS | `/tmp/skill-errors`                                                                 |
| Windows       | `%TEMP%\skill-errors` (typically `C:\Users\<user>\AppData\Local\Temp\skill-errors`) |

Detect the platform and use the appropriate base path:

```bash
# Unix (Linux / macOS)
err_dir="/tmp/skill-errors/$(date +%Y-%m-%d)"
mkdir -p "$err_dir"
err_file="$err_dir/$(date +%H-%M-%S)_<skill-name>_errors.md"
```

```powershell
# Windows (PowerShell)
$errDir = "$env:TEMP\skill-errors\$(Get-Date -Format 'yyyy-MM-dd')"
New-Item -ItemType Directory -Force -Path $errDir | Out-Null
$errFile = "$errDir\$(Get-Date -Format 'HH-mm-ss')_<skill-name>_errors.md"
```

### Log file format

```markdown
# Skill Error Log: <skill-name>
**Date:** <yyyy-mm-dd HH:MM:SS>
**Agent:** orchestrator | subagent (<role if applicable>)
**Skill path:** <path/to/skill>

---

## Entry 1: <short title>

**Instruction source:** <file:line or command that was followed>
**Instruction text:** "<exact text or close paraphrase of what was read>"
**Action taken:** <what the agent did based on that instruction>
**Expected outcome:** <what the instruction implied would happen>
**Actual outcome:** <what actually happened, including error text>
**Interpretation:** <how the agent understood the instruction and why it
took the action it did>

---

## Entry 2: ...
```

### Subagent responsibility

Subagents SHALL write to the same date directory using their own timestamped
file. The orchestrator does not need to collect or merge subagent logs — the
date directory structure naturally groups them.

### When NOT to log

Don't log issues caused by the user's project (compilation errors in their
code, missing user dependencies, etc.). Only log issues caused by the skill
itself: its documentation, its scripts, its CLIs, its templates, or its
reference files.