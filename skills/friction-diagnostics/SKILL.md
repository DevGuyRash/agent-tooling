---
name: Friction Diagnostics
description: >-
  REQUIRED for every task. Log every error, failure, unexpected outcome,
  or friction encountered — no exceptions. Sessions initialize lazily on
  first friction event; do not create a session unless you have something
  to log. Covers: (1) Any tool, command, script, or build step that fails
  or produces unexpected results, (2) Any instruction, workflow, or
  environment that behaves differently than expected, (3) Code bugs,
  compilation errors, test failures, or runtime exceptions, (4) MCP
  server, subagent, or integration misbehavior, (5) User-requested
  friction or diagnostic reporting, (6) Any problem, error, or divergence
  from expected behavior during task execution. If anything goes wrong,
  it gets logged here. Do not skip this skill.
compatibility: Designed for filesystem-capable coding agents. Deterministic helpers require POSIX sh on Unix-like systems or PowerShell on Windows. No network required.
metadata:
  author: generated-template
  version: "2.0.0"
  category: diagnostics
  tags: friction,logging,postmortem,troubleshooting
---

# Friction Diagnostics

This skill creates durable friction logs that a later agent can inspect and fix from the temp directory. Keep entries concise and concrete. Record the what and why. Do not put proposed fixes inside the log.

## When to use this skill

You SHALL use this skill for every task where friction occurs. Every error, failure, unexpected outcome, code bug, test failure, compilation error, runtime exception, or friction of any kind gets logged here.

- Every error or unexpected outcome — log it immediately when it happens.
- Every code bug, test failure, build failure, or runtime crash — log it.
- Every instruction that was wrong, ambiguous, or misleading — log it.
- Subagents that encounter friction — they auto-join the orchestrator's session.

There is no threshold for "important enough to log." If it went wrong, log it. But do not initialize a session unless you have something to log.

## Available scripts

- `<skills-file-root>/scripts/init-log.sh` / `<skills-file-root>/scripts/init-log.ps1` — create the task directory plus the current agent's log file and adjacent descriptor.
- `<skills-file-root>/scripts/report-friction.sh` / `<skills-file-root>/scripts/report-friction.ps1` — append one structured entry with auto-categorization.
- `<skills-file-root>/scripts/categorize.sh` / `<skills-file-root>/scripts/categorize.ps1` — classify an event as `surface/mode/run_effect`.
- `<skills-file-root>/scripts/build-index.sh` / `<skills-file-root>/scripts/build-index.ps1` — rebuild `INDEX.md` for a task directory.

## Workflow

WHEN any error, failure, bug, test failure, compilation error, runtime exception, unexpected outcome, or friction of any kind occurs THEN you SHALL immediately log it. Do not skip logging because the issue seems minor or is "just a code bug" — log everything.

You have two options for logging friction:

**Option A — Single-command (preferred).** Call `report-friction.sh` directly with `--task-summary`, `--agent`, and `--skill-path`. The script auto-initializes a session on first call, and subsequent agents with the same task summary automatically join the existing session:

```sh
sh <skills-file-root>/scripts/report-friction.sh \
  --task-summary "Investigate MCP routing failures" \
  --agent orchestrator \
  --skill-path "<skills-file-root>" \
  --title "Dispatch role slug mismatch" \
  --instruction-source "SKILL.md:160" \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE>" \
  --action-taken "Ran mpcr protocol dispatch --role architecture" \
  --expected-outcome "The CLI returns the architecture prompt." \
  --actual-outcome "error: unknown dispatch role: architecture" \
  --interpretation "I treated the domain table label as the CLI role slug."
```

**Option B — Explicit init.** Call `init-log.sh` first if you want to set up the session before any friction occurs (e.g. to configure `--capture-mode` or `--storage-mode`):

```sh
eval "$(sh <skills-file-root>/scripts/init-log.sh \
  --task-summary "Investigate MCP routing failures" \
  --agent orchestrator \
  --skill-path "<skills-file-root>")"
```

Then log friction with `--log-file "$FRICTION_LOG_FILE"` as before.

**Session reuse.** When `--task-id` is not provided, `init-log.sh` automatically discovers and reuses an existing session with the same task summary slug. This means subagents do not need explicit `--task-id` plumbing — they join the orchestrator's session automatically. Pass `--no-reuse` to force a fresh session.

WHEN the same issue repeats without materially new evidence THEN you SHALL NOT add a duplicate entry.

WHEN category selection is uncertain THEN you SHOULD let the categorizer choose the closest `surface/mode/run_effect` and keep the uncertainty in `Interpretation`.

WHEN overriding classification axes THEN you SHALL use only the values defined in `references/taxonomy.md`. You SHALL NOT invent new values for surface, mode, run_effect, guidance_quality, evidence_type, or confidence — the scripts fall back silently on invalid values, which degrades aggregation.

WHEN writing the Interpretation field THEN you SHALL describe what you understood the instruction or context to mean, what specific language led to that reading, and why it was a reasonable reading at the time. You SHALL NOT use the Interpretation field to diagnose the root cause, propose a fix, or editorialize.

WHEN a subagent participates THEN it automatically joins the orchestrator's session via slug-based discovery. Each subagent gets its own log file and descriptor within the shared task directory. You do not need to pass `--task-id` explicitly — session reuse is automatic.

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

- Read `references/logging-spec.md` when you need the full rules for what to log and how much detail is enough.
- Read `references/taxonomy.md` when you want to understand or override the automatic categories.
- Read `references/examples.md` when you want concrete good-vs-bad examples.
- Read `references/integration.md` when you want an `AGENTS.md` snippet or subagent propagation pattern.

## Definition of done

WHEN friction was encountered during a task THEN you SHALL leave behind:

- A task directory under the system temp root (created only when friction is logged).
- Log files for agents that reported friction (not for agents with zero friction).
- A descriptor next to each reporting agent log file.
- Entries that capture instruction source, action, expected outcome, actual outcome, and interpretation.
- No fix proposals inside log entries.
- A current `INDEX.md` file for later remediation.

WHEN no friction was encountered THEN no task directory or files SHALL be created.
