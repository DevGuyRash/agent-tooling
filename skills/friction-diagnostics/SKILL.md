---
name: friction-diagnostics
description: >-
  Use this skill when the task requires durable, structured reporting of friction
  encountered by an agent or subagent: skill and instruction mismatches, MCP or
  server issues, tool or script failures, code or logic missteps, data-contract
  problems, environment surprises, workflow handoff gaps, or ambiguous
  requirements. It creates per-top-level-task logs under the system temp
  directory, auto-categorizes each entry, and records what was read, what was
  tried, what happened, and how the situation was interpreted. Do not use it
  for pure bug fixing without a logging requirement, or for failures caused only
  by the user's project unless the agent's instructions, tools, or workflow
  contributed to the friction.
compatibility: Designed for filesystem-capable coding agents. Deterministic helpers require POSIX sh on Unix-like systems or PowerShell on Windows. No network required.
metadata:
  author: generated-template
  version: "1.0.0"
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
- `<skills-file-root>/scripts/categorize.sh` / `<skills-file-root>/scripts/categorize.ps1` — classify an event as `surface/mode/impact`.
- `<skills-file-root>/scripts/build-index.sh` / `<skills-file-root>/scripts/build-index.ps1` — rebuild `INDEX.md` for a task directory.

## Workflow

WHEN the user explicitly asks for durable friction reporting, OR repository guidance requires it, OR later remediation would benefit from a structured record, THEN you SHALL initialize a task log before substantive work begins.

WHEN you are on Linux or macOS THEN you SHALL run:

```sh
eval "$(sh <skills-file-root>/scripts/init-log.sh \
  --task-summary "Investigate MCP routing failures" \
  --agent orchestrator \
  --skill-path "<skills-file-root>")"
```

WHEN you are on Windows THEN you SHALL run:

```powershell
& "<skills-file-root>/scripts/init-log.ps1" -TaskSummary "Investigate MCP routing failures" -Agent orchestrator -SkillPath "<skills-file-root>"
```

WHEN a friction event occurs and it is not solely a user-project failure THEN you SHALL append one entry with `<skills-file-root>/scripts/report-friction.sh` or `<skills-file-root>/scripts/report-friction.ps1`.

WHEN the same issue repeats without materially new evidence THEN you SHALL NOT add a duplicate entry.

WHEN category selection is uncertain THEN you SHOULD let the categorizer choose the closest `surface/mode/impact` and keep the uncertainty in `Interpretation`.

WHEN a subagent participates THEN you SHALL reuse the same task ID and task directory values, but initialize a separate log file for that agent. Re-pass those values explicitly via `--task-id` or read them from `SESSION.txt`; do not assume exported environment variables persist across separate agent commands.

WHEN the task ends, OR after a batch of appended entries, THEN you SHOULD refresh `INDEX.md` with `<skills-file-root>/scripts/build-index.sh` or `<skills-file-root>/scripts/build-index.ps1`.

## Example append

```sh
sh <skills-file-root>/scripts/report-friction.sh \
  --log-file "$FRICTION_LOG_FILE" \
  --title "Dispatch role slug mismatch" \
  --instruction-source "SKILL.md:160" \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the domain-specific prompt." \
  --action-taken "Ran mpcr protocol dispatch --role architecture" \
  --expected-outcome "The CLI returns the architecture prompt." \
  --actual-outcome "error: unknown dispatch role: architecture" \
  --interpretation "I treated the domain table label as the CLI role slug."
```

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
