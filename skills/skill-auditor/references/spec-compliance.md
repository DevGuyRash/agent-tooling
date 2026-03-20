# Spec Compliance

AGENTS.md authoring conventions reframed as auditor checks. Use this
reference to systematically evaluate a skill against the specification.

WHEN checking spec compliance THEN you SHALL run `scripts/spec_check.sh`
before reasoning about qualitative rules.

---

## `<skills-file-root>` usage

**Source:** AGENTS.md §Skill authoring: `<skills-file-root>`

WHEN writing or editing a skill THEN you SHALL use `<skills-file-root>` as
the path prefix for all references to files within the skill directory
(scripts, references, assets). It resolves to the directory containing the
skill's `SKILL.md`.

**Check:** Search SKILL.md and reference files for hardcoded absolute paths
or relative paths that bypass `<skills-file-root>`. Flag any path that
embeds a literal skill directory location.

---

## Frontmatter and naming

**Source:** AGENTS.md §Skill authoring: frontmatter and naming

Script coverage: `scripts/spec_check.sh` validates slug format, title-case
name, name-slug correspondence, H1 match, and trigger list pattern.

Qualitative checks beyond the script:

- The description lead sentence states what the skill **does** (capability),
  not "Use this skill when..." — that framing belongs in the trigger list.
- Each numbered trigger item is a discrete, keyword-rich scenario an agent
  can match against a user's request.
- The description does not contain implementation details (temp dirs,
  internal data structures, categorization axes).
- The description does not contain narrative prose that buries triggers in
  flowing sentences.
- IF the skill has common false-positive triggers THEN the description ends
  with a short negative trigger ("Do not use for X").
- The description is under 1024 characters (silent-skip threshold).

---

## File hygiene

**Source:** AGENTS.md §Skill authoring: file hygiene

Script coverage: `scripts/spec_check.sh` checks LF line endings on all
text files, executable permission on shell scripts, and shebang presence.

All text files shipped in a skill — scripts, source, configs, protocol
data, references, templates — SHALL use LF (`\n`) line endings, never CRLF
(`\r\n`). Shell scripts additionally SHALL have executable permission
(`chmod +x`) and a valid shebang (e.g., `#!/usr/bin/env sh`).

---

## Name consistency (docs ↔ CLI)

**Source:** AGENTS.md §Skill authoring: name consistency between docs and CLI

Qualitative checks:

- Every name in documentation (role names, phase names, mode names,
  parameter values) SHALL be the exact string the CLI or API accepts.
- One canonical form per name, used everywhere: SKILL.md, reference docs,
  CLI `--help`, error messages, and protocol outputs.
- IF a CLI accepts named values THEN it SHALL offer a way to list them.
- IF documentation uses a human-friendly name that differs from the CLI
  slug THEN the documentation SHALL include an explicit mapping table.
- Before shipping, every named value mentioned in docs has been executed
  against the CLI.

---

## Error messages for agents

**Source:** AGENTS.md §Skill authoring: error messages designed for agents

Qualitative checks:

- No stack backtraces in normal errors. Error output is short, actionable,
  and context-efficient.
- Error messages include valid alternatives when input doesn't match a
  known value.
- Errors are 1-3 lines. Extra detail is behind a `--verbose` flag.
- Errors follow a consistent pattern: `error: <what>` / `hint: <fix>`.

---

## Progressive disclosure and context budgets

**Source:** AGENTS.md §Skill authoring: progressive disclosure and context budgets

Script coverage: `scripts/spec_check.sh` validates SKILL.md under 500
lines and reference files under 300 lines.

Qualitative checks:

- SKILL.md is a router, not a manual: it answers what the skill is, what
  workflow the agent is in, and what to read next — then stops.
- SKILL.md does not contain detailed procedures, full rubrics, or extended
  specifications (those belong in `references/`).
- Reference files are loaded one at a time via conditional triggers.
- Each fact lives in exactly one place. Duplicated rules, procedures, or
  constraints across SKILL.md and references are flagged.
- Reference files do not point to other reference files (no nesting).
- References over 300 lines include a table of contents.
- Peak context (SKILL.md + one reference) is under ~8,000 tokens.

---

## Subagent dispatch prompt design

**Source:** AGENTS.md §Skill authoring: subagent dispatch prompt design

Qualitative checks:

- The dispatch prompt is self-contained: task, scope, forbidden actions,
  output format template, and agent identity are all included.
- The dispatch prompt explicitly lists forbidden actions (no
  orchestrator-level commands).
- The dispatch prompt includes an explicit output template, not prose
  describing what to return.
- WHEN multiple dispatch roles exist THEN all roles share the same
  structural template with domain-specific content swapped in.
- Roles with less than 60% of the median prompt depth are flagged as
  likely too shallow.

---

## Output size discipline

**Source:** AGENTS.md §Skill authoring: output size discipline

Qualitative checks:

- CLI/script output defaults to compact (JSON on one line, summaries not
  full dumps).
- Commands with unbounded output offer filtering and pagination flags.
- Metadata and content are requestable separately.
- No single command produces more than 5,000 characters without a compact
  mode option.

---

## Cold-start readiness

**Source:** AGENTS.md §Skill authoring: cold-start readiness

Qualitative checks:

- The skill is usable without installing a toolchain, compiling source, or
  downloading large dependencies on first run.
- IF compiled tools are included THEN a pre-built binary is shipped and the
  wrapper prefers it over building from source.
- IF runtime dependencies are required THEN they are documented in the
  `compatibility` field and installation is automatic and silent.
- Scripts in `scripts/` are self-contained or clearly document their
  dependencies. Script source never enters the agent's context — only
  output does.

---

## Integration testing

**Source:** AGENTS.md §Skill authoring: integration testing across skills

Qualitative checks:

- WHEN the skill references or depends on another skill's outputs THEN the
  integration point is tested end-to-end.
- Run Skill A's setup → run Skill B's verification on Skill A's output →
  confirm zero failures without manual intervention.

---

## Idempotency and state isolation

**Source:** AGENTS.md §Skill authoring: idempotency and state isolation

Script coverage: `scripts/spec_check.sh` checks for `trap` handler
presence in shell scripts.

Qualitative checks:

- Identical re-runs on the same unchanged input produce byte-identical
  output.
- Non-deterministic output (timestamps, random IDs) is avoided in default
  output or deterministically seeded.
- Scripts that create temporary files clean them up via a `trap` handler on
  EXIT, INT, and TERM.
- WHEN a skill documents "create X" THEN re-running when X exists is
  safe — either no-op or overwrite with identical content.

---

## Error recovery

**Source:** AGENTS.md §Skill authoring: error recovery

Qualitative checks:

- WHEN a workflow has 3+ steps THEN each step's success or failure is
  independently detectable (non-zero exit, output marker, or state file).
- WHEN a step fails THEN the skill documents whether to retry, restart, or
  abort.
- Scripts do not exit 0 when a significant sub-task failed silently.
- WHEN partial output exists from a failed run THEN re-running does not
  corrupt it or produce mixed old/new results.

---

## Credential safety

**Source:** AGENTS.md §Skill authoring: credential safety

Script coverage: `scripts/spec_check.sh` checks for secret-pattern files
(`.env`, `credentials.*`, `*secret*`, `*token*`).

Qualitative checks:

- Scripts do not echo, log, or print credentials in normal or error output.
- Error messages do not include full command lines with credential flags or
  headers.
- WHEN a script uses `set -x` THEN tracing is disabled around
  credential-handling sections.
- WHEN a skill accepts credentials THEN it prefers CLI flags over
  environment variables and documents the credential flow.
- Scripts do not use `eval` on user-provided input.
