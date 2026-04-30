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

## GitOps Workflow drift control

WHEN you edit files under `skills/gitops-workflow/` AND the change affects top-level commands, aliases, routing modes, or help discovery THEN you SHALL update the same change in `scripts/gitops-help.sh`, `SKILL.md`, `references/SCRIPT_ROUTING.md`, and the targeted tests.

WHEN command discovery is needed for `skills/gitops-workflow/` THEN you SHALL treat `scripts/gitops-help.sh --json` as the canonical agent-facing discovery surface.

You SHALL NOT add another manually maintained command catalog or alias inventory for `skills/gitops-workflow/` unless runtime behavior requires it.


---

## Skill authoring: frontmatter and naming

Every skill's `SKILL.md` starts with YAML frontmatter. The `name` and
`description` fields are required by the spec and have strict constraints.

### Name field

The `name` field is the **display name** shown to users in skill listings
and selection UIs. It is title-cased with spaces. The **directory name**
(the folder containing `SKILL.md`) is the invocation slug — that's what
users type after `/` to trigger the skill.

Directory naming rules (the slug):

- Lowercase alphanumeric characters and hyphens only (`a-z`, `0-9`, `-`)
- Max 64 characters
- Must not start or end with `-`
- Must not contain consecutive hyphens (`--`)

The `name` field is the title-cased equivalent of the directory slug:

| Directory (slug)        | `name:` (display)         |
| ----------------------- | ------------------------- |
| `code-review`           | `Code Review`             |
| `rust-development`      | `Rust Development`        |
| `docker-architect`      | `Docker Architect`        |
| `espanso-dynamic-forms` | `Espanso Dynamic Forms`   |
| `gitops-workflow`       | `GitOps Workflow`         |
| `friction-diagnostics`  | `Friction Diagnostics`    |

The H1 heading in the SKILL.md body (`# ...`) should match the `name`
field exactly.

### Description field

The description is the single most important line in a skill. It's the
primary mechanism every platform uses to decide whether to activate the
skill — agents see descriptions for all available skills at startup and
match against the user's request.

**Hard constraint:** max **1024 characters**. Skills that exceed this limit
fail to load entirely — no warning, no truncation, just a silent skip.
Measure your description after editing:

```bash
python3 -c "
import yaml
with open('SKILL.md') as f:
    parts = f.read().split('---', 2)
    d = yaml.safe_load(parts[1]).get('description', '')
    print(f'{len(d)} / 1024 chars')
"
```

#### Two-part structure (required pattern)

Every description follows two parts:

1. **Lead sentence** — a capability statement describing what the skill
   does (not "Use this skill when..."). This gives the agent a quick
   "what does this do" signal.
2. **Numbered trigger list** — `"Use when the task involves: (1)... (2)...
   (N) Any task involving X."` Each numbered item is a discrete,
   keyword-rich scenario the agent can scan and match against.

Optionally end with a short negative trigger ("Do not use for X") if the
skill has common false-positive triggers that need guarding against.

#### Mandatory trigger variant

Some skills must fire every time a condition is met — the agent should not
treat activation as optional. The standard two-part structure uses passive,
opt-in language ("Use when the task involves…") that lets the agent decide
whether to bother. For mandatory skills, replace that with imperative
language that removes agent discretion.

The mandatory pattern has four parts that work together — removing any
one weakens the trigger enough for agents to skip it:

1. **Imperative opener** — lead with `REQUIRED` plus the activation
   condition. This is the strongest signal an agent parses from a
   description.
2. **Prohibition** — immediately follow with a `do not <verb> without this
   skill active` clause. This closes the escape route where the agent
   decides it can handle the task itself.
3. **Keyword trigger list** — `Covers: (1)... (2)...` enumerates scope
   with the same numbered items as the standard pattern, but under
   mandatory framing reads as "all of these are covered" rather than
   "pick one to opt in."
4. **Closing command** — end the description with a direct imperative that
   restates the trigger (`Do not skip this skill.` or
   `If the task involves X, use this skill.`). Agents that skim the middle
   still hit the bookend.

The extra framing consumes character budget — measure against the
1024-character hard limit (see above) after every edit.

Use this pattern only when the user needs the skill to always fire for its
domain. If the agent can produce a correct result without the skill — even
if slower or less polished — use the standard opt-in two-part structure
instead. Most skills should use the standard pattern.

##### When to use mandatory vs standard

| Use mandatory when | Use standard when |
|-|-|
| Skipping the skill produces wrong or unsafe output | The skill is one of several valid approaches |
| The skill enforces constraints the agent wouldn't know on its own (lint profiles, TDD workflow, compliance) | The skill adds convenience but isn't required for correctness |
| The skill's triggers overlap with tasks the agent would attempt without any skill (general coding, general debugging) | The skill's domain is narrow enough that keyword matching alone is reliable |

##### Good example (mandatory pattern)

```yaml
description: >-
  REQUIRED when any part of the task touches Rust code or Rust tooling —
  do not write, review, debug, or scaffold Rust without this skill active.
  Covers: (1) Writing new Rust code, features, or bugfixes,
  (2) Reviewing Rust pull requests or enforcing Rust coding standards,
  (3) Setting up Rust CI/CD pipelines or GitHub Actions,
  (4) Debugging Rust compilation errors or borrow-checker issues, or
  (5) Any task where the primary language is Rust (.rs files).
  If the task involves Rust, use this skill.
```

Why this works: the agent sees `REQUIRED` as the first token (part 1), a
prohibition that blocks self-handling (part 2), a keyword-rich trigger list
(part 3), and a closing command (part 4). All four parts reinforce the
same signal from different positions in the text.

#### Good example (standard pattern)

```yaml
description: >-
  Generate hardened, production-ready Docker architecture including
  Dockerfiles, Compose stacks, and Swarm deploy configs. Use when the
  task involves: (1) Writing or improving a Dockerfile or multi-stage
  build, (2) Containerizing an application, (3) Creating or modifying
  compose.yaml or Docker Swarm deployments, (4) Hardening container
  security, or (5) Any task involving Docker, containers, or container
  orchestration.
```

Why this works: the lead sentence tells the agent what the skill produces.
Each numbered item is a concrete scenario with keywords an agent can match
against a user's request. The catch-all `(5)` covers edge cases.

#### Bad examples

```yaml
# Too vague — no trigger keywords, agent must guess
description: Helps with Docker stuff.

# Narrative prose — no scannable trigger points
description: >-
  Use this skill when something you followed did not work as the
  available instructions implied it would. The core pattern is: you
  read something, acted on it, and the outcome diverged from what you
  expected. This applies across any surface.

# Implementation details instead of triggers
description: >-
  Creates per-task logs under the system temp directory, auto-categorizes
  each event along surface/mode/run_effect axes, and records what was
  read, what was tried, and what happened.
```

The narrative example buries triggers in flowing sentences that are hard
to decompose programmatically. The implementation example describes *how*
the skill works instead of *when* to use it.

#### What NOT to put in the description

- **Implementation details** (temp dirs, categorization axes, internal
  data structures) — these belong in the SKILL.md body.
- **Narrative prose** explaining the conceptual pattern — use numbered
  triggers instead.
- **Long negative-trigger lists** — one short sentence at the end is
  enough; detailed "do not use" guidance belongs in the SKILL.md body.

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

### CLI-served self-documentation

Skills with CLIs SHOULD implement progressive disclosure via CLI commands.
The CLI serves as a just-in-time guidance router: the agent runs a command
to get exactly the instructions needed for its current step, rather than
loading entire reference files.

The recommended pattern:

1. **TOML manifest for routing metadata.** Phase names, domain IDs,
   activation triggers, hints — structured data the CLI can query.
2. **Markdown for detailed content.** Full domain specs, phase procedures,
   scoring rules stay in `references/*.md`. The CLI extracts sections by
   heading on demand using `sed`/`awk`.
3. **SKILL.md as fallback router.** "Run `<cli> <command>` for guidance.
   IF the CLI is unavailable, read `references/X.md` instead."

This pattern is demonstrated by the skill-auditor's `audit-skill` CLI and
the code-review skill's `mpcr` protocol CLI. Use it when a skill has:
- Multiple phases or modes with distinct guidance per phase
- Enumerable configuration (domains, roles, traits)
- Deterministic check scripts that benefit from a unified runner

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

## Skill authoring: idempotency and state isolation

Scripts SHALL leave no residual state after completion. An agent that re-runs
a script and gets different results (because temp files, caches, or lock
files were left behind) silently corrupts its workflow.

Rules:

1. **Identical re-runs.** WHEN a script runs twice on the same unchanged
   input, THEN output SHALL be byte-identical. Non-deterministic output
   (timestamps, random IDs) SHALL be avoided in default output or
   deterministically seeded.

2. **Temp file cleanup.** Scripts that create temporary files SHALL clean
   them up via a `trap` handler on EXIT, INT, and TERM. After normal or
   abnormal termination, zero artifacts SHALL remain in `/tmp/` or the
   skill directory.

3. **Safe re-creation.** WHEN a skill documents "create X," THEN re-running
   when X already exists SHALL be safe — either a no-op or an overwrite
   with identical content.

---

## Skill authoring: error recovery

Multi-step workflows SHALL document recovery paths for mid-workflow failures.
An agent that encounters a failure at step 3 of 7 needs to know: retry this
step? restart from step 1? abort entirely?

Rules:

1. **Per-step detectability.** WHEN a workflow has 3+ steps, THEN each
   step's success or failure SHALL be independently detectable (non-zero
   exit code, output marker, or state file).

2. **Recovery documentation.** WHEN a step fails, the skill SHALL document
   whether to retry that step, restart from the beginning, or abort.

3. **No silent success.** Scripts SHALL NOT exit 0 when a significant
   sub-task failed silently. Exit code 0 means "everything worked."

4. **Partial output safety.** WHEN partial output exists from a failed run,
   THEN re-running SHALL NOT corrupt the partial output or produce mixed
   old/new results.

---

## Skill authoring: credential safety

Skills SHALL NOT commit, log, or leak credentials. A script that prints an
API key in error output (e.g., the full `curl` command with
`Authorization: Bearer <key>`) is a security incident.

Rules:

1. **No committed secrets.** Files matching secret patterns (`.env`,
   `credentials.*`, `*secret*`, `*token*`) SHALL be in `.gitignore` or
   SHALL NOT contain actual credentials.

2. **No credential leakage.** Scripts SHALL NOT echo, log, or print
   credentials in normal or error output. Error messages SHALL NOT include
   full command lines that contain credential flags or headers.

3. **No debug tracing around credentials.** WHEN a script uses `set -x`,
   THEN it SHALL disable tracing around credential-handling sections.

4. **Prefer CLI flags.** WHEN a skill accepts credentials, THEN it SHALL
   prefer CLI flags over environment variables, and SHALL document the
   credential flow.

5. **No eval on user input.** Scripts SHALL NOT use `eval` on user-provided
   input (command injection risk).

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

```bash
<tmp>/<skill-name>/<yyyy-mm-dd>/<HH-MM-SS>_errors.md
```

Use the Linux temp base path:

```bash
err_dir="/tmp/skill-errors/<skill-name>/$(date +%Y-%m-%d)"
mkdir -p "$err_dir"
err_file="$err_dir/$(date +%H-%M-%S)_errors.md"
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

Subagents SHALL write to the same skill/date directory using their own
timestamped file. The orchestrator does not need to collect or merge
subagent logs — the skill/date directory structure naturally groups them.

### When NOT to log

Don't log issues caused by the user's project (compilation errors in their
code, missing user dependencies, etc.). Only log issues caused by the skill
itself: its documentation, its scripts, its CLIs, its templates, or its
reference files.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **agent-skills** (9115 symbols, 17155 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/agent-skills/context` | Codebase overview, check index freshness |
| `gitnexus://repo/agent-skills/clusters` | All functional areas |
| `gitnexus://repo/agent-skills/processes` | All execution flows |
| `gitnexus://repo/agent-skills/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |
| Work in the Tests area (615 symbols) | `.claude/skills/generated/tests/SKILL.md` |
| Work in the Scripts area (141 symbols) | `.claude/skills/generated/scripts/SKILL.md` |
| Work in the Assets area (73 symbols) | `.claude/skills/generated/assets/SKILL.md` |
| Work in the Cluster_136 area (49 symbols) | `.claude/skills/generated/cluster-136/SKILL.md` |
| Work in the Cluster_114 area (37 symbols) | `.claude/skills/generated/cluster-114/SKILL.md` |
| Work in the Validate_output_contract area (36 symbols) | `.claude/skills/generated/validate-output-contract/SKILL.md` |
| Work in the Cluster_113 area (35 symbols) | `.claude/skills/generated/cluster-113/SKILL.md` |
| Work in the Cluster_143 area (22 symbols) | `.claude/skills/generated/cluster-143/SKILL.md` |
| Work in the Cluster_99 area (19 symbols) | `.claude/skills/generated/cluster-99/SKILL.md` |
| Work in the Cluster_177 area (19 symbols) | `.claude/skills/generated/cluster-177/SKILL.md` |
| Work in the Cluster_109 area (18 symbols) | `.claude/skills/generated/cluster-109/SKILL.md` |
| Work in the Cluster_165 area (18 symbols) | `.claude/skills/generated/cluster-165/SKILL.md` |
| Work in the Cluster_181 area (18 symbols) | `.claude/skills/generated/cluster-181/SKILL.md` |
| Work in the Validate_ area (18 symbols) | `.claude/skills/generated/validate/SKILL.md` |
| Work in the Cluster_139 area (17 symbols) | `.claude/skills/generated/cluster-139/SKILL.md` |
| Work in the Cluster_141 area (16 symbols) | `.claude/skills/generated/cluster-141/SKILL.md` |
| Work in the Cluster_166 area (16 symbols) | `.claude/skills/generated/cluster-166/SKILL.md` |
| Work in the Cluster_116 area (15 symbols) | `.claude/skills/generated/cluster-116/SKILL.md` |
| Work in the Cluster_88 area (13 symbols) | `.claude/skills/generated/cluster-88/SKILL.md` |
| Work in the Evaluate_dockerfile_policy area (13 symbols) | `.claude/skills/generated/evaluate-dockerfile-policy/SKILL.md` |

<!-- gitnexus:end -->
