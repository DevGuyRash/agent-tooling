# Repo-wide agent notes

This file contains cross-cutting constraints that apply regardless of language or skill. Language/toolchain-specific workflows live in the corresponding plugin-local skill `SKILL.md` files under `plugins/<plugin-name>/skills/<skill-name>/`.

Skills in this repo follow the portable core defined by the [Open Agent Skills standard](https://agentskills.io/specification). Host-specific packaging, catalog visibility, shortening, omission, activation, and execution behavior remain governed by the exact supported host surface.

For Agent Skill and plugin quality, apply repository-level authorities only where they are genuinely cross-cutting. Keep plugin-local contracts scoped to the plugin that ships them.

## Governing Architecture

These rules apply only when you create or revise instructions for another AI. They govern the instruction system, not the surrounding answer.

The executor's intelligence is the resource. Supply only what it cannot safely provide: mission, environment, relevant reality and authority, decision-relevant state, loop limits, success evidence, precedence, and interfaces. Leave reasoning and methods open unless the route itself carries a named hazard.

Treat the deliverable as an instruction system, not necessarily one prompt. Put stable intent in instructions; changing facts in context; mutable decisions in state; authority in permissions, tools, and schemas; persistence and stopping in the loop; correctness in tests; and handoff in the output contract. Do not duplicate controls.

Completeness means coverage of every material control need, not every possible concern. Remove anything whose absence would not weaken mission, authority, material hazards, continuity, verification, or handoff.

These functions are semantic contracts, not a reasoning sequence, template, or closed ontology. Omit, combine, or add as needed.

### Mission

Define the outcome, whom it serves, the current decision horizon, and what distinguishes done from plausible. Separate required properties from suggested methods. Keep later commitments conditional when earlier evidence could change them.

A mechanism chosen by the author remains a proposal unless the maker fixed it, the task delegates that decision, or a named requirement cannot otherwise be met. Binding force attaches to the required property and hazard. Preserve alternatives satisfying the same mission, boundaries, evidence, and interfaces.

### Environment

Supply what the executor cannot safely infer, inspect, or rediscover: resources, limits, permissions, dependencies, hazards, external effects, and consequential gaps. Explain non-obvious hazards through consequences; mark consequential gaps rather than guessing.

Keep consequential information's source and authority unambiguous. Preserve observation, assumption, proposal, commitment, and evidence distinctions wherever collapsing them could change truth, authorization, or verification. Do not surface the taxonomy merely to prove it exists. Encode any mandatory consequence once.

### State

Keep action-changing state recoverable across turns and handoffs: objective, settled decisions, assumptions, evidence, dependencies, blockers, alternatives, progress, and reopening conditions.

Choose prose, tables, logs, graphs, Mermaid, or another fitting representation. Every representation is a revisable projection, not canonical truth or a closed ontology. Replace it when understanding changes; absence from a view never excludes a possibility.

### Boundaries

Define prohibited outcomes, authority limits, approvals, and constraints whose violation would cause material harm, invalidate the work, or exceed the mandate. Prefer external enforcement where more reliable. State each boundary once.

### Loop

Define progress, continuation, stopping, completion, retry, escalation, handoff, budgets, and blocked behavior. Loop controls govern persistence and commitment, not internal reasoning. Bind only the current evidence horizon. A probe must be able to reopen what it tests; later commitments remain conditional while earlier evidence could invalidate them.

### Verification

Define observable evidence of completion, correctness, safety, and handoff. Prefer executable checks and/or observable evidence. Assertion alone is not evidence. Match verification strength to consequence.

### Precedence

Resolve foreseeable collisions among mission, authority, safety, correctness, scope, and reversibility. Do not invent exhaustive branches for unknown space. Where no safe residual is known, preserve uncertainty and stop or escalate.

### Output Contract

Specify audience, destination, interface or format, completion evidence, and conditions for claiming success. Impose structure or style only when it improves use.

### Binding Language

Use natural prose for purpose, facts, rationale, definitions, and open judgment. Address obligations directly to the executor. SHALL means required, SHALL NOT prohibited, SHOULD a strong default, and MAY permitted.

Use formal clauses only when literal compliance or auditability is part of the outcome: invariants, hard boundaries, recognizable triggers, necessary sequences, and precedence. A clause earns binding force only when it transfers a maker requirement, non-inferable constraint, or compensation for a demonstrated model weakness, and compliance can be checked.

Bind outcomes, not pathways. Prescribe sequence only when order carries a named hazard. Say each obligation once. Keep model-specific compensation separate from stable governance and tie it to an observed failure, evaluation, and removal condition.

Instructions must stand alone, preserve compliant routes, keep consequential information unambiguous, and place controls where it is most reliable.

Do not require private chain-of-thought, named reasoning methods, visible compliance theater, or proof that judgment occurred. Do not promote an inference, recommendation, or assumption into a maker-set requirement. Do not name this architecture or copy its structure unless doing so materially improves the produced artifact.

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

Some CLIs offer a `--print-env` flag that outputs the values you need for subsequent commands. Capture them in one command, then pass as flags:

```bash
# Example: registration prints IDs to reuse later
tool register --print-env
# Output: WORKER_ID=deadbeef SESSION_ID=sess0001
# Use those values as explicit flags in the next command:
tool update --worker-id deadbeef --session-id sess0001 --status IN_PROGRESS
```

**Option C: chain commands in a single shell invocation**:

```bash
export MY_SESSION_ID=abc123 && cd /some/project && tool update --use-env
```

This applies to any CLI that offers `--use-env` or environment-based configuration. Those patterns are designed for shell scripts and CI pipelines where the entire pipeline runs in one shell session. When used by agents — where each command is a separate process — environment-based configuration provides no benefit.

**Always prefer explicit CLI flags over environment variables when running from agents.**

---

## Skill authoring: `<skills-file-root>`

When writing or editing a skill, use either relative paths or `<skills-file-root>` for references to files within the same skill directory (scripts, references, assets). `<skills-file-root>` resolves to the directory containing the skill's `SKILL.md`.

## Plugin installation and portability

Installing plugins into the local CLIs goes through `scripts/install-all` (or `just install-all`): it is the developer bootstrap helper for this repository's marketplace, not a workstation desired-state authority. It resolves the exact source, adds missing marketplace/plugin state, and updates only a differing version/source-digest identity. It supports `--include`/`--exclude` CSV globs, `--codex-only`/`--claude-only`, `--dry-run`, and explicit `--force`. Host catalogs MAY differ; WHEN filters select no plugin for one enabled host but do select a plugin for another THEN you SHALL skip marketplace and install changes for the empty host. The registered marketplaces track GitHub `DevGuyRash/agent-tooling@main`, so a local change reaches the installed caches only after it is pushed; sessions opened before an actual plugin replacement keep running the previously cached plugin version. Codex subprocesses inherit `CODEX_HOME`; Claude replacement removes only the selected `--claude-scope` declaration.

`--source` persists as the marketplace's durable source, not a one-off: the CLIs register whatever you pass until explicitly replaced. `--source <local path>` is the testing affordance for unpushed changes and leaves both CLIs on a non-canonical directory marketplace that must later be reconciled to GitHub. WHEN installing for anything but testing local unpushed changes THEN you SHALL omit `--source`. A source mismatch SHALL fail before mutation. WHEN intentionally changing the durable source THEN you SHALL use `--replace-marketplace`; replacement invalidates the matching receipt identity and rematerializes selected plugins. Use `--force` only for an intentional selected reinstall or downgrade.

Host publication must match executable capability:

WHEN a plugin can execute on both hosts THEN you SHALL publish and verify both host variants.

WHEN a plugin depends on a host-native runtime, host-only instruction model, or host-only security boundary THEN you SHALL publish it only for the capable host and document that constraint in the plugin README and root inventory. You SHALL NOT ship a nonfunctional host shell solely to keep marketplace catalogs identical.

WHEN preparing a final push that changes anything under `plugins/` THEN you SHALL round-trip the changed plugin through both targets with `scripts/plugin_port.py`; for an intentionally host-specific plugin, the unpublished target is a structural portability audit rather than a publication artifact:

```bash
# Round-trip each changed plugin through the other host and back (conversion fidelity):
python3 scripts/plugin_port.py roundtrip plugins/<name> --to codex --tmp .local/tmp/rt-codex
python3 scripts/plugin_port.py roundtrip plugins/<name> --to claude --tmp .local/tmp/rt-claude

# Validate each converted variant for its target host. Host-specific converted
# output remains scratch evidence and is not added to the other marketplace.
python3 scripts/plugin_port.py validate .local/tmp/rt-codex/<name>-codex --host codex
python3 scripts/plugin_port.py validate .local/tmp/rt-claude/<name>-claude --host claude

# Converter unit tests; live CLI checks when local tools are available:
just test-plugin-port
just test-plugin-port-live
```

Roundtrips default to strict conversion and validate the actual second-hop plugin before succeeding. IF any roundtrip, validation, or test step fails THEN you SHALL fix the plugin (or the converter) and re-verify before the push. You SHALL NOT commit the conversion artifacts — they are scratch output and stay under `.local/tmp/`.

---

## Skill authoring: frontmatter and naming

Every skill's `SKILL.md` starts with YAML frontmatter. The `name` and `description` fields are required by the spec and have strict constraints.

### Name field

The `name` field MUST be the lowercase invocation slug and MUST exactly match the directory name that contains `SKILL.md`.

Directory naming rules (the slug):

- Lowercase alphanumeric characters and hyphens only (`a-z`, `0-9`, `-`)
- Max 64 characters
- Must not start or end with `-`
- Must not contain consecutive hyphens (`--`)

The body H1 (`# ...`) and `agents/openai.yaml` display name are the human-facing, title-cased equivalents of the slug:

| Directory / `name:` slug | H1 / display name       |
| ------------------------ | ----------------------- |
| `rust-development`       | `Rust Development`      |
| `docker-architect`       | `Docker Architect`      |
| `espanso-dynamic-forms`  | `Espanso Dynamic Forms` |
| `software-development`   | `Software Development`  |
| `friction-diagnostics`   | `Friction Diagnostics`  |

The H1 heading in the `SKILL.md` body (`# ...`) and the OpenAI display metadata should match each other exactly.

### Description field

The description is the skill's portable retrieval surface: it states what the skill does and when it applies. Exact catalog exposure, shortening, omission, and activation behavior are host-specific.

The portable format requires a non-empty description of at most **1024 parsed characters**. New skills in this repo SHOULD use the smallest description that still gives reliable routing evidence. Measure your description after editing:

```bash
python3 -c "
import yaml
with open('SKILL.md') as f:
    parts = f.read().split('---', 2)
    d = yaml.safe_load(parts[1]).get('description', '')
    print(f'{len(d)} / 1024 chars')
"
```

#### Description structure

Descriptions should front-load the capability, then include the strongest positive triggers and the most important sibling exclusions. Numbered trigger lists are optional. Use the smallest wording that still makes routing clear and preserves signal when a host shortens visible descriptions.

#### Mandatory trigger variant

Some skills must fire every time a condition is met — the agent should not treat activation as optional. The standard two-part structure uses passive, opt-in language ("Use when the task involves…") that lets the agent decide whether to bother. For mandatory skills, replace that with imperative language that removes agent discretion.

The mandatory pattern usually combines these parts:

1. **Imperative opener** — lead with `REQUIRED` plus the activation condition. This is the strongest signal an agent parses from a description.
2. **Prohibition** — immediately follow with a `do not <verb> without this skill active` clause. This closes the escape route where the agent decides it can handle the task itself.
3. **Keyword trigger span** — `Covers: ...` or an equivalent compact scope summary that names the bounded mandatory surface.
4. **Closing command** — end the description with a direct imperative that restates the trigger (`Do not skip this skill.` or `If the task involves X, use this skill.`). Agents that skim the middle still hit the bookend.

The extra framing consumes character budget — measure against the 1024-character hard limit (see above) after every edit.

Use this pattern only when the user needs the skill to always fire for its domain. If the agent can produce a correct result without the skill — even if slower or less polished — use the standard opt-in two-part structure instead. Most skills should use the standard pattern.

##### When to use mandatory vs standard

| Use mandatory when | Use standard when |
| --- | --- |
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

Why this works: the agent sees `REQUIRED` as the first token (part 1), a prohibition that blocks self-handling (part 2), a keyword-rich trigger list (part 3), and a closing command (part 4). All four parts reinforce the same signal from different positions in the text.

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

Why this works: the lead sentence tells the agent what the skill produces. The trigger phrases give concrete routing evidence an agent can match against a user's request without wasting description budget.

#### Bad examples

```yaml
# Too vague — no trigger keywords, agent must guess
description: Helps with Docker stuff.

# Narrative prose — activation boundary is difficult to distinguish
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

The narrative example does not distinguish its activation boundary from nearby tasks. The implementation example describes _how_ the skill works instead of _when_ to use it.

#### What NOT to put in the description

- **Implementation details** (temp dirs, categorization axes, internal data structures) — these belong in the SKILL.md body.
- **Narrative prose** that obscures the activation boundary — use the clearest compact structure for the actual routing evidence.
- **Long negative-trigger lists** — one short sentence at the end is enough; detailed "do not use" guidance belongs in the SKILL.md body.

Test the description with realistic positive, negative, and near-neighbor prompts. If the evidence does not show a reliable activation boundary, rewrite it.

---

## Skill authoring: file hygiene

All text files shipped in a skill — scripts, source, configs, protocol data, references, templates — SHALL use LF (`\n`) line endings, never CRLF (`\r\n`).

CRLF in a shell script is a silent blocker: the shebang becomes `#!/usr/bin/env sh\r` and Linux resolves that as a missing binary. An agent encountering this wastes its entire turn on a confusing error. The same problem affects Python scripts, TOML configs loaded at runtime, and any file `cat`-piped into another command.

Before committing any skill file:

```bash
# Detect CRLF in the skill directory
find <skill-dir> -type f \( -name '*.sh' -o -name '*.py' -o -name '*.rs' \
  -o -name '*.toml' -o -name '*.yml' -o -name '*.md' \) \
  -exec grep -Plc '\r' {} + 2>/dev/null
```

If any files match, fix them: `sed -i 's/\r$//' <file>`. Enforce this in CI or use `.gitattributes` with `* text=auto eol=lf`.

Shell scripts additionally SHALL have executable permission (`chmod +x`) and a valid shebang (e.g., `#!/usr/bin/env sh`).

---

## Skill authoring: name consistency between docs and CLI

Every name that appears in a skill's documentation — role names, phase names, mode names, parameter values — SHALL be the exact string the CLI or API accepts. If the CLI accepts `architecture-critic`, the docs say `architecture-critic`, not `Architecture` or `architecture`.

Name mismatches between documentation and implementation are the single most common agent failure mode. An agent reads a domain table listing "Architecture," tries `--role architecture`, gets an error, tries `--role Architecture`, gets another error, and either fabricates a workaround (breaking protocol consistency) or enters a retry loop burning tokens.

Rules:

1. **One canonical form.** Pick one representation for each name and use it everywhere: SKILL.md, reference docs, CLI `--help`, error messages, and protocol outputs. If the CLI normalizes input (e.g., lowercases and replaces hyphens with underscores), document the canonical form the user should type, not the internal form.

2. **Discovery command.** If a CLI accepts a set of named values, it SHALL offer a way to list them. For example, `tool dispatch --list` or `tool --help` showing valid values. An agent that hits an invalid name should be one command away from finding the valid names — not searching through docs.

3. **Mapping tables.** When documentation uses a human-friendly name (e.g., "Architecture") that differs from the CLI slug (e.g., `architecture-critic`), the documentation SHALL include an explicit mapping table showing both forms. Don't force the agent to infer the mapping.

4. **Test every name.** Before shipping a skill, execute every named value mentioned in the docs against the CLI. This catches drift between docs and implementation that's invisible during code review.

---

## Skill authoring: error messages designed for agents

When a skill includes a CLI or script that agents will invoke, error output SHALL be short, actionable, and context-efficient. Agents pay for every character of error output — it consumes their working context.

Rules:

1. **No stack backtraces in normal errors.** A backtrace for "unknown role name" is never useful to an agent. Set `RUST_BACKTRACE=0` or equivalent in wrapper scripts, or structure error handling to emit clean messages.

2. **Include valid alternatives in error messages.** When input doesn't match a known value, the error should say what the valid values are:

   ```bash
   error: unknown role "architecture"
   valid roles: architecture-critic, contract-guardian, ...
   ```

   This turns a dead-end error into a self-correcting one.

3. **Keep errors concise.** Put diagnostic detail that is not needed for recovery behind a `--verbose` flag.

4. **Consistent format.** Errors from a skill's CLI should follow a uniform pattern so agents can parse them mechanically:

   ```bash
   error: <what went wrong>
   hint: <what to do instead>
   ```

---

## Skill authoring: progressive disclosure and context budgets

Agent context windows are finite and expensive. Every token of instruction that an agent holds is a token that can't be used for the actual task. Skills SHALL be designed so the agent only loads the instructions it needs for the current step, not everything up front.

### The three-layer loading model

Skills follow a three-level progressive disclosure system. Each layer loads at a different time and serves a different purpose.

| Layer | Loaded when | Target size | Purpose |
| --- | --- | --- | --- |
| **Metadata** (name + description in frontmatter) | Always in context | Keep only retrieval evidence | Trigger detection — does this skill apply? |
| **SKILL.md body** | When skill triggers | Keep the always-loaded route focused | Routing: what workflow am I in? What do I read next? |
| **Bundled resources** (`references/`, `scripts/`, `assets/`) | On demand | Keep each resource focused on its loading condition | Detail: full procedures, rubrics, templates, domain-specific guidance |

The critical principle: **the agent reads deeper only when needed.** SKILL.md tells the agent which reference or references the current decision requires, without loading unrelated material.

### SKILL.md is a router, not a manual

SKILL.md answers three questions and stops:

1. "What is this skill and when does it trigger?"
2. "What workflow am I in?" (mode selection based on user input)
3. "What do I read next?" (pointer to the right reference file or script)

SKILL.md should NOT contain detailed procedures, full rubrics, or extended specifications unless they are needed on every activation. Put conditional detail in `references/` files so the agent does not pay its context cost when it is irrelevant.

### Reference files are the primary disclosure mechanism

The `references/` directory is how most skills deliver just-in-time instructions. There are three proven patterns for organizing them:

**Pattern 1: Conditional loading with a reference index.** SKILL.md contains a table mapping situations to files. The agent reads only the row that matches.

```markdown
## Reference index

You SHALL load only the references needed for the current task.

| File                       | When to read                       |
| -------------------------- | ---------------------------------- |
| `references/guidelines.md` | Phase 1 of any workflow            |
| `references/migration.md`  | Converting a non-Rust tool to Rust |
| `references/monorepo.md`   | Working in a Rust workspace        |
```

**Pattern 2: Domain-variant organization.** When a skill supports multiple domains or frameworks, split references by variant. The agent loads only the variant it needs.

```bash
cloud-deploy/
├── SKILL.md          (workflow selection + routing)
└── references/
    ├── aws.md        (loaded only for AWS tasks)
    ├── gcp.md        (loaded only for GCP tasks)
    └── azure.md      (loaded only for Azure tasks)
```

**Pattern 3: Inline links at point of relevance.** SKILL.md contains reference links right where the agent needs them, woven into the workflow narrative. Good for smaller skills.

```markdown
## Output and clipboard policy

For low-latency expansions, prefer `print_only` when the replacement
payload is already emitted by script output.

Read: [references/clipboard-latency.md](references/clipboard-latency.md)
```

All three patterns achieve the same goal: the agent loads only the focused references needed for the current decision instead of everything at once.

### CLI-served protocols (advanced pattern)

Some skills include a CLI that serves instructions dynamically — for example, `tool protocol orchestrator` outputs orchestration guidance, and `tool protocol dispatch --role X` outputs a role-specific prompt. This is a powerful progressive disclosure mechanism because the CLI can tailor output to the current phase or role.

When a skill has this kind of CLI, the `references/` files serve as fallback for when the CLI is unavailable (not built, wrong platform, missing dependency). The SKILL.md should say:

```markdown
You SHALL run `tool protocol orchestrator` for guidance.
IF the CLI is unavailable, read `references/orchestrator-fallback.md` instead.
```

The CLI output and the fallback reference SHALL contain the same information. They are two delivery mechanisms for one source of truth, not two documents that drift apart over time. Ideally the CLI embeds the reference content directly (e.g., from TOML or markdown files compiled into the binary) so they are literally the same text.

### Each fact lives in exactly one place

The most insidious context problem is duplication: the same rule, procedure, or constraint described in SKILL.md AND a reference file AND a CLI output. The agent pays for all three copies, and when they inevitably drift apart, the agent gets conflicting instructions.

Common duplication to watch for:

- **Workflow steps** narrated in SKILL.md and repeated in detail in a reference file. SKILL.md should give a 1-line summary and point to the reference; the reference has the detail.
- **Rules and constraints** (concurrency caps, forbidden actions, cleanup requirements) stated in SKILL.md and again in reference docs. State the rule once; the other location says "see X."
- **Command quick-references** in SKILL.md that reproduce what `--help` or a script already provides. If the agent can run a command to get the information, SKILL.md doesn't need to list it.

When in doubt, ask: "If I change this fact, how many files do I need to edit?" If the answer is more than one, there's duplication.

### Reference file sizing and depth

SKILL.md can point to as many reference files as needed — that's the whole point of the reference index pattern. The constraint is on _nesting_: a reference file should not point to another reference file. If Reference A tells the agent to read Reference B, which tells it to read Reference C, the agent is in a context spiral — accumulating instructions without making progress. All references should be reachable directly from SKILL.md, not through other references. If a reference needs information from another file, inline it or restructure.

When a reference becomes difficult to navigate or contains independently triggered material, add navigation or split it into focused files with separate conditional triggers from SKILL.md.

### Measuring your context budget

Before shipping a skill, measure what the agent actually loads during a typical invocation:

```bash
# Measure every document in the skill
find <skill-dir> -name '*.md' -exec wc -c {} + | sort -n
# Report characters as a reproducible proxy when no governing tokenizer is named
```

The key metric is **peak context** — the maximum number of skill-instruction tokens the agent holds at any single point during the workflow. This is NOT the sum of all files (the agent doesn't load them all at once); it's SKILL.md plus whichever reference file(s) the agent has loaded at the busiest point.

Treat measured characters, physical lines, estimated tokens, file counts, and peak loaded context as review signals. They justify a change only when the active loading path wastes material context or harms task value. An estimated token count is never a release gate unless the governing authority names the tokenizer or the host reports the exact count.

### CLI-served self-documentation

Skills with CLIs SHOULD implement progressive disclosure via CLI commands. The CLI serves as a just-in-time guidance router: the agent runs a command to get exactly the instructions needed for its current step, rather than loading entire reference files.

The recommended pattern:

1. **TOML manifest for routing metadata.** Phase names, domain IDs, activation triggers, hints — structured data the CLI can query.
2. **Markdown for detailed content.** Full domain specs, phase procedures, scoring rules stay in `references/*.md`. The CLI extracts sections by heading on demand using `sed`/`awk`.
3. **SKILL.md as fallback router.** "Run `<cli> <command>` for guidance. IF the CLI is unavailable, read `references/X.md` instead."

Use this pattern when a skill has:

- Multiple phases or modes with distinct guidance per phase
- Enumerable configuration (domains, roles, traits)
- Deterministic check scripts that benefit from a unified runner

---

## Skill authoring: subagent dispatch prompt design

Before claiming what a delegated worker does or does not receive, inspect the selected host's actual inheritance, mounted files, ambient instructions, tools, permissions, and conversation behavior. A fresh context may still inherit consequential state, while an isolated worker may still need complete authoritative sources.

Give each delegated function a role-complete instruction: its mission, legitimate authoritative inputs, environment, authority and effect boundaries, observable completion evidence, and the narrowest real output interface. Transfer what the role cannot safely infer; do not pass controller hypotheses, preferred methods, sibling outputs, hidden resolution logic, or broader orchestration state unless they are legitimately part of the role or tested deployment.

Do not impose a semantic response template solely for controller convenience. Preserve native artifacts and free-form judgment when they are the real interface. Require fields, files, identifiers, or structure only when an actual downstream consumer, deterministic transport, custody boundary, or demonstrated failure makes them necessary; keep raw payloads when a normalizer or extractor is used.

Prevent delegated functions from invoking controller-only mutations or expanding scope. State prohibitions that are materially reachable in the selected host, and enforce them through permissions or isolated workspaces when that is more reliable than prose.

---

## Skill authoring: output size discipline

When a skill's CLI or script produces output that an agent will consume, that output SHALL be sized for agent context, not human terminals.

Rules:

1. **Default to compact output.** JSON on one line, not pretty-printed. Summaries, not full dumps. An agent can request verbose output with a flag if needed.

2. **Offer filtering and pagination.** If a command can return unbounded data (e.g., all session reports with full contents), provide flags to limit output: `--summary-only`, `--max-items N`, `--fields id,status`.

3. **Separate metadata from content.** If a command returns both structural metadata (IDs, statuses) and large content (full report text), let the agent request them separately rather than dumping everything at once.

4. **Measure your outputs.** Run every command your skill documents and inspect whether the default output contains material the agent does not need. Add filtering or a compact mode when observed output wastes consequential context.

---

## Skill authoring: cold-start readiness

A skill SHALL be usable without requiring the agent to install a toolchain, compile source code, or download large dependencies on first run. Cold-start cost must be proportionate to the task and visible when it cannot be avoided.

If a skill includes compiled tools (Rust binaries, Go binaries, etc.):

- Ship a pre-built binary for the target platform alongside the source.
- The wrapper script should prefer the pre-built binary and fall back to building from source only if the binary is missing or outdated.

If a skill depends on runtime tools (Python packages, npm modules):

- Document the dependencies in the SKILL.md `compatibility` field.
- Prefer vendored or self-contained scripts over tools requiring `pip install` or `npm install`.
- If installation is unavoidable, make it automatic and silent (the agent should not need to know it's happening).

An agent that spends 3 minutes installing Rust and building a binary is an agent that's not doing the user's task.

### Script self-containment

Scripts in `scripts/` SHALL be self-contained or clearly document their dependencies. When an agent runs a script, the script's source code never enters the context window — only its output does. This makes scripts significantly more token-efficient than having the agent write equivalent code inline. A 200-line Python script that produces 5 lines of output costs 5 lines of context, not 200. Lean into this: prefer bundled scripts over inline instructions whenever the task involves deterministic logic, data transformation, or validation that would otherwise consume agent context to reason through.

---

## Skill authoring: integration testing across skills

When a skill references or depends on another skill's outputs (e.g., a code review skill that uses a Rust skill's scaffold to set up lint configs), the integration point SHALL be tested end-to-end.

Common failure: Skill A scaffolds configuration files. Skill B's verification step runs lint checks. The scaffolded config is stricter than the scaffolded test files, so verification fails immediately after setup. Neither skill is broken in isolation — the failure only appears at the integration boundary.

Before shipping interconnected skills:

1. Run Skill A's setup.
2. Run Skill B's verification on Skill A's output.
3. Confirm zero failures without manual intervention.

---

## Skill authoring: idempotency and state isolation

Scripts SHALL leave no residual state after completion. An agent that re-runs a script and gets different results (because temp files, caches, or lock files were left behind) silently corrupts its workflow.

Rules:

1. **Identical re-runs.** WHEN a script runs twice on the same unchanged input, THEN output SHALL be byte-identical. Non-deterministic output (timestamps, random IDs) SHALL be avoided in default output or deterministically seeded.

2. **Temp file cleanup.** Scripts that create temporary files SHALL clean them up via a `trap` handler on EXIT, INT, and TERM. After normal or abnormal termination, zero artifacts SHALL remain in `/tmp/` or the skill directory.

3. **Safe re-creation.** WHEN a skill documents "create X," THEN re-running when X already exists SHALL be safe — either a no-op or an overwrite with identical content.

---

## Skill authoring: error recovery

Multi-step workflows SHALL document recovery paths for mid-workflow failures. An agent that encounters a failure at step 3 of 7 needs to know: retry this step? restart from step 1? abort entirely?

Rules:

1. **Per-step detectability.** Each step whose failure would change the next safe action SHALL have independently detectable success or failure (non-zero exit code, output marker, or state file).

2. **Recovery documentation.** WHEN a step fails, the skill SHALL document whether to retry that step, restart from the beginning, or abort.

3. **No silent success.** Scripts SHALL NOT exit 0 when a significant sub-task failed silently. Exit code 0 means "everything worked."

4. **Partial output safety.** WHEN partial output exists from a failed run, THEN re-running SHALL NOT corrupt the partial output or produce mixed old/new results.

---

## Skill authoring: credential safety

Skills SHALL NOT commit, log, or leak credentials. A script that prints an API key in error output (e.g., the full `curl` command with `Authorization: Bearer <key>`) is a security incident.

Rules:

1. **No committed secrets.** Files matching secret patterns (`.env`, `credentials.*`, `*secret*`, `*token*`) SHALL be in `.gitignore` or SHALL NOT contain actual credentials.

2. **No credential leakage.** Scripts SHALL NOT echo, log, or print credentials in normal or error output. Error messages SHALL NOT include full command lines that contain credential flags or headers.

3. **No debug tracing around credentials.** WHEN a script uses `set -x`, THEN it SHALL disable tracing around credential-handling sections.

4. **Prefer CLI flags.** WHEN a skill accepts credentials, THEN it SHALL prefer CLI flags over environment variables, and SHALL document the credential flow.

5. **No eval on user input.** Scripts SHALL NOT use `eval` on user-provided input (command injection risk).
