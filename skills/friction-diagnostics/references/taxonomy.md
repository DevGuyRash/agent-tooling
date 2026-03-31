# Taxonomy

The categorizer uses three axes. This avoids a giant brittle enum while still producing deterministic, grep-friendly labels.

## Numeric scales

Canonical scale definitions (labels and aliases) live in `friction-event-schema.json` under `x-scales`. The tables below expand on the intended meaning of each level.

### Confidence (1–5)

How certain the agent was about its interpretation when the friction occurred.

| Value | Label | Meaning |
|-------|-------|---------|
| 1 | wild guess | No real basis; proceeding blind |
| 2 | low | Some signal but mostly uncertain |
| 3 | moderate | Plausible reading, reasonable doubt |
| 4 | high | Strong basis; minor uncertainty only |
| 5 | near certain | Evidence strongly supports this reading |

### Guidance quality (0–4)

How clear or misleading the available guidance was.

| Value | Label | Meaning |
|-------|-------|---------|
| 0 | N/A | No guidance was involved |
| 1 | misleading | Guidance actively suggested the wrong action |
| 2 | ambiguous | Guidance could be read multiple ways |
| 3 | partial | Guidance was correct but incomplete |
| 4 | clear | Guidance was unambiguous and accurate |

## Surface

Where the friction primarily showed up.

### `instructions`

**Scope:** Friction originating from prompt text, AGENTS.md guidance, dispatch instructions, inline runbooks, or any non-skill documentation that directs agent behavior.

**Typical signals:**
- An AGENTS.md directive is ambiguous or contradictory
- A referenced runbook or doc does not exist
- Dispatch instructions use undefined terminology
- Two instruction sources give conflicting guidance

**Boundary:** When the instruction lives inside a SKILL.md or a skill's reference files, use `skill` instead. When the friction is with external API documentation (not agent-facing instructions), the surface depends on what broke — if the agent followed stale docs and the API call failed, use `external-service`; if the docs themselves were the instruction source and were ambiguous, use `instructions`.

### `skill`

**Scope:** Friction originating from SKILL.md files, skill reference documents, skill templates, or skill-specific routing.

**Typical signals:**
- A skill's SKILL.md points to a command or slug that does not exist
- A skill reference doc contradicts its SKILL.md
- A skill template has missing fields or wrong structure
- A skill's described workflow does not match what its scripts actually do
- A skill points to a script path or flag that the script does not support

**Boundary:** `skill` is the instruction and routing layer around a skill. Actual script files, even inside a skill package, are `script`. When a skill wraps a third-party tool and the friction is in the tool itself (not the skill's invocation of it), use `tool`. When the skill's instructions *about* the tool are wrong, use `skill`. When the friction is in an MCP tool that the skill references, use `mcp` if the MCP tool misbehaved, or `skill` if the skill's instructions about the MCP tool were wrong.

### `mcp`

**Scope:** Friction with MCP (Model Context Protocol) server connections, tool invocations, response handling, or tool descriptions.

**Typical signals:**
- An MCP tool returns data that does not match its description
- A tool response shape differs from what the description implied
- Connection to an MCP server fails or times out
- A tool description overpromises capabilities
- Tool parameters in the description do not match accepted parameters

**Boundary:** If a skill's instructions about an MCP tool are wrong, use `skill`. If the MCP tool itself misbehaves relative to its own description or documented contract, use `mcp`. If you are calling an API directly (not through MCP), use `external-service`.

### `tool`

**Scope:** Friction with CLIs, SDK commands, editor commands, build systems, compilers, package managers, linters, formatters, and other executable tooling outside of bundled scripts and MCP servers.

**Typical signals:**
- A CLI command fails with an error its `--help` does not explain
- A tool's `--help` output contradicts its actual behavior
- A build step breaks with a confusing error
- A package manager cannot resolve dependencies
- A tool's flag is documented but rejected at runtime

**Boundary:** If the tool is bundled as a repository or skill script (`.sh`, `.ps1`), use `script`. If the tool is an MCP server, use `mcp`. Use `tool` for standalone executables and CLIs that are not bundled scripts.

### `script`

**Scope:** Friction with bundled scripts or repository scripts — files like `scripts/verify.sh`, `build.sh`, `.ps1` scripts, or any executable script that is part of the project or skill.

**Typical signals:**
- A script crashes with a syntax error or unset variable
- A script produces wrong output silently
- A script works on one shell (bash) but fails on another (dash)
- A script wraps a test suite whose results are nondeterministic
- A script's documented behavior does not match its actual behavior

**Boundary:** If the script is a standalone CLI tool that is installed system-wide (not bundled), use `tool`. If the script is part of a skill package, use `script` — the surface is about the script itself, not the skill's reference to it. If the friction is that the skill *points to a script that does not exist*, use `skill` (the instruction is wrong, not the script).

### `code`

**Scope:** Friction with agent-authored or agent-edited code paths and their runtime behavior — functions, modules, classes, and their contracts.

**Typical signals:**
- A function's docstring promises one return type but delivers another
- Agent-edited code runs without error but produces divergent downstream behavior
- A module's public interface changed without updating callers
- A test passes but the tested behavior is wrong

**Boundary:** When the friction is in reasoning or assumptions rather than in the code's runtime behavior, use `logic`. When the friction is in a standalone script file, use `script`. Use `code` when the code itself (source files, compiled modules) behaves differently from its documented contract.

### `logic`

**Scope:** Friction from reasoning errors, wrong assumptions, inverted conditions, sequencing mistakes, or algorithm choice — where the system does something technically valid but semantically wrong.

**Typical signals:**
- An exit-code check is inverted (retries on success instead of failure)
- A default value is wrong for the context
- A sorting comparator has reversed order
- An assumption about input format leads to wrong processing
- An algorithm is structurally correct but operates on a wrong premise

**Boundary:** When the code crashes or raises an error, use `code` or `script` (something broke). Use `logic` when the code *runs successfully* but produces the wrong result because of a reasoning or assumption error. The distinction: `code` friction is "it broke," `logic` friction is "it ran but did the wrong thing because the reasoning was flawed."

### `data`

**Scope:** Friction from schemas, field names, file formats, shape mismatches, serialization issues, and data-contract disagreements.

**Typical signals:**
- A field uses a different type than consumers expect (epoch vs ISO 8601)
- A file format is CSV but the parser expects TSV
- A serialized payload has a different shape than the consuming code assumes
- A field name changed between versions and the consumer uses the old name

**Boundary:** Do not use `data` when the friction is with a network service — if the mismatch is in an API response, use `external-service`. Use `data` when the friction is in a local data contract, serialized file, payload structure, or schema definition. The distinction: `data` is about the shape and format of information, not the transport layer.

### `environment`

**Scope:** Friction from the operating system, filesystem, paths, dependencies, permissions, container configuration, sandbox limits, or runtime environment.

**Typical signals:**
- A required binary is not installed (`command not found`)
- A path does not exist or has wrong permissions
- An environment variable is missing or wrong
- A container image is missing expected packages
- A script assumes bash but the shell is dash
- Filesystem is read-only in a sandboxed environment

**Boundary:** If a skill's instructions reference a dependency that the environment lacks, the surface depends on the root cause: if the instructions are wrong about what is available, consider `instructions` or `skill`; if the environment genuinely lacks something it should have, use `environment`. Do not use `environment` for tool bugs — a tool that is installed but malfunctions is `tool`, not `environment`.

### `external-service`

**Scope:** Friction with HTTP APIs, auth flows, network services, rate limits, webhooks, and other external service interactions.

**Typical signals:**
- An API returns an unexpected status code
- A rate limit blocks progress
- Auth tokens expire or are rejected
- A webhook payload does not match its documented structure
- A service is intermittently unavailable

**Boundary:** If the friction is with an MCP tool that wraps an API, use `mcp` (the MCP layer is the proximate friction point). If you are calling the API directly, use `external-service`. For auth-related friction, the mode (`auth` vs `other`) matters — a 403 from rate limiting is `external-service/other`, not `external-service/auth`.

### `workflow`

**Scope:** Friction from routing, delegation, handoffs, context loss, ordering mistakes, and multi-agent coordination.

**Typical signals:**
- A handoff between orchestrator and subagent loses essential context
- A subagent re-does work the orchestrator already completed
- Task ordering causes a step to run before its dependency
- Context compaction removes information the next step needs
- A delegation message is too vague for the subagent to act on

**Boundary:** If the friction is that the instructions (AGENTS.md, SKILL.md) about the workflow are wrong, use `instructions` or `skill`. Use `workflow` when the workflow structure itself causes the friction — context was not passed, ordering was wrong, or delegation was incomplete.

### `unknown`

**Scope:** Fallback surface when no reliable primary surface can be inferred from the available evidence.

Use `unknown` only when genuinely unable to identify where the friction originated. This should be rare — most friction has an identifiable source. If you are uncertain between two surfaces, pick the one closest to the root cause and explain the ambiguity in `reading`.

---

## Mode

What kind of breakdown happened. WHEN overriding mode THEN you SHALL use one of the values listed below. You SHALL NOT invent new mode values — use `other` when none of the specific modes fit.

### `ambiguity`
An instruction, description, or contract can be read multiple ways and the agent picked the wrong interpretation or could not determine which was correct. Signal: "unclear", "ambiguous", "underspecified", "not sure which".

### `contradiction`
Two sources of truth disagree — a `--help` flag list contradicts actual behavior, two docs give conflicting values, or a description promises something the implementation rejects. Signal: "contradicts", "inconsistent", "does not match docs".

### `name-resolution`
A name, slug, identifier, or reference could not be resolved — a command name is wrong, a dispatch role does not exist, or an enum value is not recognized. Signal: "unknown dispatch role", "unrecognized", "no such subcommand".

### `missing`
A required resource does not exist — a file is absent, a dependency is not installed, a referenced doc cannot be found. Signal: "not found", "no such file", "missing", "does not exist".

### `permission`
The agent has the right identity but lacks the required permissions for the operation. Signal: "permission denied", "operation not permitted".

### `auth`
Authentication or authorization failed — credentials are wrong, tokens are expired, or the identity is rejected. Signal: "unauthorized", "forbidden", "401", "403", "token".

### `timeout`
An operation did not complete within its time budget. Signal: "timed out", "timeout", "deadline exceeded".

### `crash`
A hard failure — a process terminated abnormally with a traceback, panic, segfault, or unhandled exception. Signal: "traceback", "panic", "crash", "exception", "segmentation fault".

### `schema`
The structure, type, or shape of data did not match what was expected — a field is the wrong type, a response has unexpected keys, or serialization produced the wrong format. Signal: "schema", "type mismatch", "parse error", "shape mismatch".

### `validation`
Input was rejected because it failed validation rules — a required field was missing, a value was out of range, or an assertion failed. Signal: "validation", "invalid", "required", "assertion failed".

### `output-mismatch`
The operation completed without error but produced the wrong result — the output differs from what was expected based on the documentation or contract. Signal: "did not match", "rendered incorrectly", "misleading output".

### `context-loss`
Essential information was lost during a handoff, compaction, or delegation — the next step lacked context it needed. Signal: "lost context", "missing context", "forgot", "compaction".

### `nondeterminism`
The same operation produces different results across runs without any input change — flaky tests, race conditions, timing-dependent behavior. Signal: "flaky", "intermittent", "nondeterministic", "sometimes".

### `performance`
An operation was unreasonably slow, hung, thrashed, or consumed excessive resources relative to expectations. Signal: "slow", "hang", "thrash", "looped", "repeated retries".

### `other`
The breakdown does not fit any of the above modes. Use `other` when the mode is genuinely novel, and explain in `reading`. Also use `other` to override a heuristic that picked a directionally wrong mode (e.g., overriding `auth` when the real cause is rate limiting).

---

## Run effect

How the run was operationally affected. WHEN overriding run effect THEN you SHALL use one of: `blocked`, `degraded`, `noisy`, `continued`. You SHALL NOT invent new run effect values.

### `blocked`
Progress stopped or the intended action could not complete. The agent had to abandon the step or wait for external resolution.

Example scenario: A script crashes on invocation — the agent cannot proceed until the script is fixed or an alternative path is found.

### `degraded`
Work continued, but with reduced correctness or reliability. The agent produced a result but it is incomplete, uses a workaround, or has lower confidence.

Example scenario: A function returns a list when a single value was expected — the code runs but downstream behavior is subtly wrong. The agent continued but the output quality was reduced.

### `noisy`
The run thrashed, retried, or wasted effort without yielding new signal. The agent spent cycles on non-productive work but was not blocked.

Example scenario: A flaky test fails on first run, passes on retry with no code change — the agent cannot tell if its fix worked and spends extra runs trying to distinguish signal from noise.

### `continued`
The run proceeded without operational disruption. This is the default when no blocking, degrading, or noisy condition was detected.

---

## Guidance quality

How clear or misleading the available guidance was. The schema stores guidance quality as a numeric value (0–4); see the Numeric scales section above for the full mapping. WHEN overriding guidance quality THEN you SHALL use one of the semantic labels or their numeric equivalents: `clear` (4), `partial` (3), `ambiguous` (2), `misleading` (1), `not-applicable` (0). You SHALL NOT invent new guidance quality values.

### `clear` (4)
The guidance was unambiguous and accurately described the actual behavior. This is the default.

### `ambiguous` (2)
The guidance was unclear, underspecified, or could be read multiple ways. The agent spent effort interpreting signals without reaching confident understanding.

Example scenario: AGENTS.md says "keep the change minimal and production ready" — the agent cannot tell if a migration is in scope and proceeds with uncertainty about whether the reviewer will accept the result.

### `misleading` (1)
The available evidence actively suggested the wrong action or interpretation. The agent was led astray, not merely confused.

Example scenario: A `--help` text lists `json` as a valid format option but the CLI rejects it — the documentation pointed the agent toward an action that was guaranteed to fail.

### `not-applicable` (0)
No guidance was involved in the friction — the event was purely operational (e.g., a timeout, a missing dependency).

---

## Examples

- `skill/name-resolution/blocked`
- `mcp/timeout/blocked`
- `instructions/ambiguity/continued`
- `data/schema/degraded`
- `workflow/context-loss/degraded`

---

## Surface selection decision tree

When you are unsure which surface to use, walk this list in order. The auto-categorizer (`categorize.sh` / `categorize.ps1`) uses the same priority — first match wins.

1. Does the friction originate from a **SKILL.md**, skill reference, skill template, or skill-specific routing?
   → `skill`

2. Does the friction originate from **AGENTS.md**, prompt text, dispatch instructions, or a referenced runbook?
   → `instructions`

3. Does the friction involve an **MCP** server, tool, or response?
   → `mcp`

4. Does the friction involve a **bundled script** (`.sh`, `.ps1`, `scripts/` directory), including scripts shipped inside a skill package?
   → `script`

5. Does the friction involve an **HTTP API**, auth flow, webhook, or network service?
   → `external-service`

6. Does the friction involve the **OS, filesystem, dependencies, permissions**, or container environment?
   → `environment`

7. Does the friction involve **data shape, schema, serialization**, or format mismatch?
   → `data`

8. Does the friction involve **delegation, handoff, routing**, or context loss between agents?
   → `workflow`

9. Does the friction involve **reasoning, assumptions, or algorithm logic** that was structurally sound but semantically wrong?
   → `logic`

10. Does the friction involve **code paths, function contracts, or runtime behavior** of agent-edited code?
    → `code`

11. Does the friction involve a **CLI, SDK command**, or standalone executable?
    → `tool`

12. None of the above → `unknown`

---

## Override examples

### Override 1: Text mentions MCP but friction is in skill instructions

An agent's SKILL.md says "call the `build_inspect` MCP tool with `--verbose` mode" but the MCP tool does not accept a `--verbose` parameter. The MCP tool is working correctly — it simply does not have that parameter. The friction is that the skill's instructions are wrong about how to call the tool.

Default categorization: `skill` — the instruction in SKILL.md is the source of friction, not the MCP tool itself.

### Override 2: Categorizer picks `tool/crash/blocked` but the crash is environmental

An agent runs a bundled linting tool that crashes with `error while loading shared libraries: libz.so.1: cannot open shared object file`. The auto-categorizer sees "crash" and picks `tool/crash/blocked`. However, the tool itself is fine — the crash is caused by a missing system library in the container image.

Override: `--surface environment` — the root cause is a missing dependency in the environment, not a bug in the tool.

---

## Heuristic notes

The auto-categorizer is deterministic and intentionally simple. It favors stable grep-friendly output over cleverness.

WHEN the automatic label is good enough THEN you SHOULD keep it.

WHEN the automatic label is directionally wrong and you have better evidence THEN you SHOULD override one or more axes with explicit flags when calling the report script.

WHEN no axis is clearly identifiable THEN you SHOULD leave the closest category in place and explain the uncertainty in `reading`.

**Important heuristic interactions:**

- The `logic` surface check looks for `assumption`, `misread`, `interpreted`, `logic`, and `reasoning`. Since many entries naturally use words like "interpreted" in the `reading` field, entries targeting a non-logic surface should avoid these trigger words in other fields (title, actual-outcome, source refs, instruction text).
- The `code` surface check also matches on `traceback`, `exception`, and `runtime`. If the friction is environmental (missing library causes a crash), these words will push the surface to `code` before reaching `environment`. Use an override in such cases.
- The `run_effect` heuristic checks for "blocked" keywords first, so entries with words like "missing" or "failed" will land on `blocked` even when the overall outcome was `degraded`. Use `--run-effect degraded` to override.
- The `guidance_quality` heuristic operates on `source_text` (instruction/expected context), not the full text. Words like "ambiguous" in the actual-outcome field do not trigger `ambiguous` guidance quality.
