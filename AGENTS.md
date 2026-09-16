# Repo-wide agent notes

This file contains cross-cutting constraints that apply regardless of language or skill. Language/toolchain-specific workflows live in the corresponding plugin-local skill `SKILL.md` files under `plugins/<plugin-name>/skills/<skill-name>/`.

Skills in this repo follow the portable core defined by the [Open Agent Skills standard](https://agentskills.io/specification). Host-specific packaging, catalog visibility, shortening, omission, activation, and execution behavior remain governed by the exact supported host surface.

For Agent Skill and plugin quality, apply repository-level authorities only where they are genuinely cross-cutting. Keep plugin-local contracts scoped to the plugin that ships them.

## Governing Architecture

When creating or revising instructions for another AI in this repository, you SHALL apply the [canonical governing architecture](plugins/agentic-design-and-evaluation/skills/foundational-knowledge/references/governing-architecture.md). That file is the sole maintained source of the charter. Its scope is authoring decisions and the instruction system produced; it does not prescribe surrounding answers or retroactively govern external targets. The adjacent foundational knowledge supplies explanatory grounds, not another repository workflow.

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

This applies to any CLI that offers `--use-env` or environment-based configuration. Those patterns are designed for shell scripts and CI pipelines where the entire pipeline runs in one shell session. When used by agents — where each command is a separate process — per-command environment configuration remains useful when it is the tool’s supported interface, but a prior command’s exported values are unavailable.

**Use an interface that explicitly supplies each command’s needed state.** CLI flags and per-command environment variables can both do this. You SHALL NOT assume that an export from an earlier command persists; choose the supported channel appropriate to the value and its protection requirements.

---

## Skill authoring: `<skills-file-root>`

When writing or editing a skill, use either relative paths or `<skills-file-root>` for references to files within the same skill directory (scripts, references, assets). This repository's `<skills-file-root>` notation denotes the directory containing `SKILL.md`; it is not a variable defined by the portable skill format. Verify the intended host or consumer's interpretation before relying on a root placeholder.

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

#### Discovery and activation

Descriptions SHOULD front-load the actual capability and recognizable requests. Include a scope distinction when it prevents likely misrouting; naming sibling skills is not required. Put dependency and composition details where the recipient needs them instead of turning retrieval metadata into an internal routing map. Keep descriptions as short as reliable discovery permits. A catchall or repeated demand to activate does not demonstrate usefulness or solve poor routing.

You SHALL require mandatory activation only when an actual user requirement, adopted contract, or demonstrated hazard requires it. State that bounded requirement and its basis directly; do not use a generic activation-pressure pattern. Preserve automatic discovery unless the user explicitly requests an explicit-only entry.

Where discovery is material, examine realistic positive, negative, and near-neighbor requests at the relevant host surface. Distinguish format validation, catalog exposure, explicit invocation, and actual implicit selection. Do not turn a fixed test roster or preferred description wording into the release criterion.

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

Document invocation names and parameter values using the forms the actual CLI or API accepts. You SHALL keep this interface consistent with its consumer. When a human-facing label differs, make the correspondence clear where the executor needs it; a table is one option.

A discovery command, help text, schema, or accessible reference SHOULD make valid values recoverable when there are consequential choices. Verify documented invocation information against the actual interface. Execute representative or changed values when that observation is authorized, safe, and necessary; exhaustive execution is not a requirement for commands with external effects or a different adequate source of evidence.

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

Design context access around the task and actual recipient. Keep essential purpose and constraints in the entry; put substantial conditional detail in supporting resources where that improves use. A short self-contained skill needs no separate router. A resource can link another resource when the relationship helps; reference depth alone is not a defect. Provide navigation, search terms, or a contents section when they make a substantial document usable, without requiring them in every file.

Keep complete relevant source material or reliable access where independent assessment can change the work. A summary or index is an aid, not a closed account of what can matter. Choose reading by the live task, broaden when needed, reuse unchanged material still in context, and recover consequential grounds after loss or change. Do not require full-corpus reading on every activation or presume a historical reading is still active knowledge.

Maintain one authoritative source for a fact or rule, and keep its navigation with that owner. Complementary controls can be useful, but copied chapter maps and procedures invite drift even when all links resolve. Public shared resources, optional capabilities, and required dependencies need distinguishable contracts; reading knowledge does not require invoking another workflow. CLI-served guidance and fallback references SHOULD derive from the same maintained source when they promise the same information. Use a CLI router only when an existing execution surface or substantial conditional content makes it useful; do not build one by default.

Declare the actual distribution boundary. Shared references may live within a complete plugin rather than be copied into every skill. Verify that the installed recipient can resolve them. Generated downstream artifacts SHALL carry the meaning, constraints, sources or reliable access, and resources their own executors need; they SHALL NOT rely on an invisible authoring conversation or undeclared local cache.

Measure the actual loading path when context cost affects the task. Characters, lines, estimated tokens, file counts, and maximum loaded material are evidence signals, not universal quality gates. Report characters as a reproducible proxy when no governing tokenizer is named. Retain useful explanatory material even when the executor could reconstruct it; assess the whole collaboration cost and outcome rather than brevity alone.

---

## Skill authoring: subagent dispatch prompt design

Before claiming what a delegated worker does or does not receive, inspect the selected host's actual inheritance, mounted files, ambient instructions, tools, permissions, and conversation behavior. A fresh context may still inherit consequential state, while an isolated worker may still need complete authoritative sources.

Give each delegated function a role-complete instruction: its mission, legitimate authoritative inputs, environment, authority and effect boundaries, observable completion evidence, and the narrowest real output interface. Transfer the relevant meaning and source material the role needs, including useful information it could otherwise reconstruct; do not pass controller hypotheses, preferred methods, sibling outputs, hidden resolution logic, or broader orchestration state unless they are legitimately part of the role or tested deployment.

A handoff supplies information and state, not understanding. The recipient SHALL reconstruct consequential understanding from the relevant original assignment and evidence; summaries orient access and do not turn the sender's interpretation into authority. Preserve completed actions and current state so reconstruction does not repeat external effects. This applies to execution plans, review packets, compaction, and continuation as well as explicit delegation. A bounded worker need not own the entire project to derive its own appropriate route or report an upstream defect.

Do not impose a semantic response template solely for controller convenience. Preserve native artifacts and free-form judgment when they are the real interface. Require fields, files, identifiers, or structure only when an actual downstream consumer, deterministic transport, custody boundary, or demonstrated failure makes them necessary; keep raw payloads when a normalizer or extractor is used.

Prevent delegated functions from invoking controller-only mutations or expanding scope. State prohibitions that are materially reachable in the selected host, and enforce them through permissions or isolated workspaces when that is more reliable than prose.

---

## Skill authoring: output size discipline

When a skill's CLI or script produces output that an agent will consume, that output SHALL be sized for agent context, not human terminals.

Rules:

1. **Default to compact output.** JSON on one line, not pretty-printed. Summaries, not full dumps. An agent can request verbose output with a flag if needed.

2. **Offer filtering and pagination.** If a command can return unbounded data (e.g., all session reports with full contents), provide flags to limit output: `--summary-only`, `--max-items N`, `--fields id,status`.

3. **Separate metadata from content.** If a command returns both structural metadata (IDs, statuses) and large content (full report text), let the agent request them separately rather than dumping everything at once.

4. **Measure relevant outputs.** Inspect representative or changed outputs when their size can affect the consumer. Use authorized execution or retained faithful evidence; do not run an external-effect command merely to measure its verbosity. Add filtering or a compact mode when it addresses observed waste.

---

## Skill authoring: cold-start readiness

You SHALL make required runtime dependencies and unavoidable first-use costs discoverable. Use the SKILL.md `compatibility` field for relevant host and dependency requirements. A script can be self-contained, use an existing runtime, or depend on explicitly supplied resources according to the task and distribution contract.

For a packaged compiled tool, the repository's adopted binary delivery policy still governs. A pre-built executable and a bounded build fallback can avoid repeated setup where supported. Do not introduce compilation, vendoring, or download machinery without a concrete delivery need.

You SHALL NOT silently install dependencies or treat their necessity as authorization. Carry out setup already authorized by the task; otherwise expose the actual missing dependency and the permission or environment change needed. State the effect and recovery route proportionately.

## Skill authoring: integration across skills

When components depend on one another's outputs or resources, you SHALL verify the material relationship at the intended consumer boundary before claiming it works. Configuration generation followed by the actual consumer's check is one useful case; it is not a required topology for every integration.

Correct evidence can include an expected refusal, a detected defect, or required human participation. Judge the outcome against the adopted interface rather than requiring zero reported failures or fully unattended execution in every workflow. Structural preservation, host ingestion, model behavior, and downstream use remain different properties.

## Skill authoring: temporary state and reruns

You SHALL give scratch state exclusive ownership, and clean up the temporary files or directories owned by the invocation on normal completion and handled termination. A private temporary directory or an equivalent runtime facility can provide that boundary. Do not follow pre-existing predictable paths into someone else's files or delete required outputs, retained evidence, or unrelated state as cleanup.

You SHALL preserve determinism and idempotency where the actual interface promises them. Identical-input reruns need not be byte-identical when the task intentionally observes changing reality or produces time-dependent records. Keep intended variation distinguishable from stale caches, mixed partial output, or unintended shared state.

For rerunnable creation or mutation, you SHALL make the existing-output and partial-failure behavior explicit where it changes safe continuation. A no-op, refusal, resume, versioned output, or authorized replacement may be correct for the actual task; identical overwrite is not a universal requirement.

---

## Skill authoring: error recovery

Multi-step workflows SHALL document recovery paths for mid-workflow failures. An agent that encounters a failure at step 3 of 7 needs to know: retry this step? restart from step 1? abort entirely?

Rules:

1. **Per-step detectability.** Each step whose failure would change the next safe action SHALL have independently detectable success or failure (non-zero exit code, output marker, or state file).

2. **Recovery documentation.** WHEN a step fails, the skill SHALL document whether to retry that step, restart from the beginning, or abort.

3. **No silent success.** Scripts SHALL NOT exit 0 when a significant sub-task failed silently. Exit code 0 SHALL mean the command fulfilled its declared interface; a diagnostic may successfully report a target defect. Missing promised evidence is not successful collection.

4. **Partial output safety.** WHEN partial output exists from a failed run, THEN re-running SHALL NOT corrupt the partial output or produce mixed old/new results.

---

## Skill authoring: credential safety

Skills SHALL NOT commit, log, or leak credentials. A script that prints an API key in error output (e.g., the full `curl` command with `Authorization: Bearer <key>`) is a security incident.

Rules:

1. **No committed secrets.** Files matching secret patterns (`.env`, `credentials.*`, `*secret*`, `*token*`) SHALL be in `.gitignore` or SHALL NOT contain actual credentials.

2. **No credential leakage.** Scripts SHALL NOT echo, log, or print credentials in normal or error output. Error messages SHALL NOT include full command lines that contain credential flags or headers.

3. **No debug tracing around credentials.** WHEN a script uses `set -x`, THEN it SHALL disable tracing around credential-handling sections.

4. **Credential channels.** You SHALL use the actual tool’s supported credential interface with the protection the task needs, and document the flow where the executor must act. Choose among secret stores, protected input channels, scoped environment variables, or supported flags according to exposure and interface constraints; shell-state persistence does not decide credential handling.

5. **No eval on user input.** Scripts SHALL NOT use `eval` on user-provided input (command injection risk).
