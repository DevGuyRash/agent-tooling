---
name: friction-diagnostics
description: >-
  Use this skill when something you followed, interpreted, or executed did not
  work as the available instructions, tools, documentation, or workflow implied
  it would. The core pattern is: you read or were told something, you acted on
  that understanding, and the outcome diverged from what the source material
  led you to expect. This applies across any surface — skills, instructions,
  MCP tools, scripts, CLIs, APIs, data contracts, environments, handoffs, or
  reasoning paths. Also use it when the user or repository guidance explicitly
  asks for durable friction reporting, or when multi-agent runs need repairable
  evidence that survives session boundaries. The skill creates per-task logs
  under the system temp directory, auto-categorizes each event along
  surface/mode/run_effect/guidance_quality axes, and records what was read,
  what was tried, what happened, and what the agent understood at the time.
  Do not use it for pure bug fixing without a logging requirement, or for
  failures caused only by the user's project unless the agent's instructions,
  tools, or workflow contributed to the friction.
compatibility: Designed for filesystem-capable coding agents. Deterministic helpers require POSIX sh on Unix-like systems or PowerShell on Windows. No network required.
metadata:
  author: generated-template
  version: "2.0.0"
  category: diagnostics
  tags: friction,logging,postmortem,troubleshooting
---

# Friction diagnostics

This skill creates durable friction logs that a later agent can inspect and fix from the temp directory. Keep entries concise and concrete. Record the what and why. Do not put proposed fixes inside the log.

## Use this skill for

- Durable diagnostic reporting across a top-level task.
- Multi-agent runs where subagents should leave repairable evidence.
- Repeated or subtle frictions that should survive context loss or session boundaries.

## Do not use this skill for

- Routine bug fixing when no durable record is needed.
- Pure user-project failures with no agent, tool, instruction, or workflow contribution.
- High-level retrospectives that do not need structured, per-event entries.

## Available scripts

- `<skills-file-root>/scripts/init-log.sh` / `<skills-file-root>/scripts/init-log.ps1` — create a task-scoped log file and task directory.
- `<skills-file-root>/scripts/report-friction.sh` / `<skills-file-root>/scripts/report-friction.ps1` — append one structured entry with auto-categorization.
- `<skills-file-root>/scripts/categorize.sh` / `<skills-file-root>/scripts/categorize.ps1` — classify an event as `surface/mode/run_effect`.
- `<skills-file-root>/scripts/build-index.sh` / `<skills-file-root>/scripts/build-index.ps1` — rebuild `INDEX.md` for a task directory.

## Workflow

WHEN the user explicitly asks for durable friction reporting, OR repository guidance requires it, OR later remediation would benefit from a structured record, THEN you SHALL initialize a task log before substantive work begins.

WHEN you are on Linux or macOS THEN you SHALL run:

```sh
eval "$(sh <skills-file-root>/scripts/init-log.sh \
  --task-summary "Investigate MCP routing failures — inspect_build returns stale metadata and dispatch roles do not resolve" \
  --agent orchestrator \
  --skill-path "<skills-file-root>")"
```

WHEN you are on Windows THEN you SHALL run:

```powershell
& "<skills-file-root>/scripts/init-log.ps1" -TaskSummary "Investigate MCP routing failures — inspect_build returns stale metadata and dispatch roles do not resolve" -Agent orchestrator -SkillPath "<skills-file-root>"
```

WHEN a friction event occurs and it is not solely a user-project failure THEN you SHALL append one entry with `<skills-file-root>/scripts/report-friction.sh` or `<skills-file-root>/scripts/report-friction.ps1`.

WHEN the same issue repeats without materially new evidence THEN you SHALL NOT add a duplicate entry.

WHEN category selection is uncertain THEN you SHOULD let the categorizer choose the closest `surface/mode/run_effect` and keep the uncertainty in `Interpretation`.

WHEN overriding classification axes THEN you SHALL use only the values defined in `references/taxonomy.md`. You SHALL NOT invent new values for surface, mode, run_effect, guidance_quality, evidence_type, or confidence — the scripts fall back silently on invalid values, which degrades aggregation.

WHEN writing the Interpretation field THEN you SHALL describe what you understood the instruction or context to mean, what specific language led to that reading, and why it was a reasonable reading at the time. You SHALL NOT use the Interpretation field to diagnose the root cause, propose a fix, or editorialize.

WHEN a subagent participates THEN you SHALL reuse the same task ID and task directory values, but initialize a separate log file for that agent. Re-pass those values explicitly via `--task-id` or read them from `SESSION.txt`; do not assume exported environment variables persist across separate agent commands.

WHEN the task ends, OR after a batch of appended entries, THEN you SHOULD refresh `INDEX.md` with `<skills-file-root>/scripts/build-index.sh` or `<skills-file-root>/scripts/build-index.ps1`.

## Example append

```sh
sh <skills-file-root>/scripts/report-friction.sh \
  --log-file "$FRICTION_LOG_FILE" \
  --title "Dispatch role slug mismatch" \
  --instruction-source "SKILL.md:160, inside the Domain routing table" \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the domain-specific prompt. The table above lists domains: Architecture, Security, Performance. No column distinguishes labels from CLI slugs." \
  --action-taken "Ran mpcr protocol dispatch --role architecture. I picked the label Architecture from the table, lowercased it, and passed it as the ROLE value." \
  --expected-outcome "The CLI prints the architecture domain prompt. The instruction says --role ROLE with the table labels listed directly above, so I expected the label to be the slug." \
  --actual-outcome "error: unknown dispatch role: architecture — exit code 1. The CLI does not list valid slugs in the error or --help." \
  --interpretation "I understood ROLE to mean the domain labels from the table directly above the instruction, because nothing in SKILL.md distinguishes labels from slugs. The phrasing Use --role ROLE immediately follows the table, which made the labels look like the intended values."
```

The Interpretation field records what you believed the instruction meant and what language led you there. It is a witness statement about your reading, not an analysis of the root cause.

## Read these only when needed

- Read `references/logging-spec.md` when you need the full rules for what to log, what not to log, and how much detail is enough.
- Read `references/taxonomy.md` when you want to understand or override the automatic categories.
- Read `references/examples.md` when you want concrete good-vs-bad examples.
- Read `references/integration.md` when you want an `AGENTS.md` snippet or subagent propagation pattern.

## Definition of done

WHEN this skill is used for a task THEN you SHALL leave behind:

- A task directory under the system temp root.
- At least one log file for each reporting agent that encountered friction.
- Entries that capture instruction source, action, expected outcome, actual outcome, and interpretation.
- No fix proposals inside log entries.
- A current `INDEX.md` file for later remediation.
