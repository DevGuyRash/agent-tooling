---
name: Friction Diagnostics
description: >-
  REQUIRED for every task. Log every error, failure, unexpected outcome,
  or friction encountered — no exceptions. Covers: (1) Any tool, command,
  script, or build step that fails or produces unexpected results, (2) Any
  instruction, workflow, or environment that behaves differently than expected,
  (3) Code bugs, compilation errors, test failures, or runtime exceptions,
  (4) MCP server, subagent, or integration misbehavior, (5) User-requested
  friction or diagnostic reporting, (6) Any problem, error, or divergence
  from expected behavior during task execution. If anything goes wrong,
  it gets logged here. Do not skip this skill.
compatibility: Designed for filesystem-capable coding agents. Deterministic helpers require POSIX sh on Unix-like systems or PowerShell on Windows. No network required.
metadata:
  author: generated-template
  version: "3.0.0"
  category: diagnostics
  tags: friction,logging,postmortem,troubleshooting
---

# Friction Diagnostics

This skill records friction as a rolling event stream. The canonical persisted data is `events.jsonl`. `INDEX.md` is a tool-managed summary view that the tooling creates and refreshes automatically.

## When to use this skill

You SHALL use this skill for every task where friction occurs.

- Every error or unexpected outcome: log it immediately.
- Every code bug, test failure, build failure, or runtime crash: log it.
- Every instruction that was wrong, ambiguous, or misleading: log it.
- Subagents and nested subagents log to the same repo-scoped rolling file by default when they are operating in the same repo.

WHEN the same issue repeats without materially new evidence THEN you SHALL NOT add a duplicate entry.

WHEN writing the `Interpretation` field THEN you SHALL describe what you understood the instruction or context to mean, what specific language led to that reading, and why that reading was reasonable at the time. You SHALL NOT use `Interpretation` to propose a fix.

## Canonical storage

Default path resolution:

- inside a git repo: `<repo>/.local/context/friction/events.jsonl`
- if a `.local*/context` directory already exists: use that existing context area
- outside a git repo: `<temp>/agent-friction/<cwd-hash>/events.jsonl`
- explicit override: `--events-file <path>`

`INDEX.md` lives next to the canonical `events.jsonl`, but agents do not create or rebuild it directly. The tool maintains it automatically after append operations.

## Available scripts

- `<skills-file-root>/scripts/report-friction.sh` / `<skills-file-root>/scripts/report-friction.ps1` — append one structured event to the canonical event stream.
- `<skills-file-root>/scripts/query-friction.sh` / `<skills-file-root>/scripts/query-friction.ps1` — filter and render the event stream.
- `<skills-file-root>/scripts/build-index.sh` / `<skills-file-root>/scripts/build-index.ps1` — internal index maintenance.
- `<skills-file-root>/scripts/categorize.sh` / `<skills-file-root>/scripts/categorize.ps1` — classify an event as `surface/mode/run_effect`.

There is no `init-log` step.

## Workflow

WHEN friction occurs THEN you SHALL call `report-friction.*` directly.

Preferred path for agents:

```sh
sh <skills-file-root>/scripts/report-friction.sh \
  --title "Dispatch role slug mismatch" \
  --instruction-source "SKILL.md:160" \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt." \
  --action-taken "Ran mpcr protocol dispatch --role architecture." \
  --expected-outcome "The CLI returns the architecture prompt." \
  --actual-outcome "error: unknown dispatch role: architecture" \
  --interpretation "I treated the visible table label as the CLI slug." \
  --anchor-kind file \
  --anchor-path "<skills-file-root>/SKILL.md" \
  --anchor-line 160
```

Optional structured-input path:

```sh
cat <<'EOF' | sh <skills-file-root>/scripts/report-friction.sh --from-json -
{
  "title": "Dispatch role slug mismatch",
  "instruction_source": "SKILL.md:160",
  "instruction_text": "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt.",
  "action_taken": "Ran mpcr protocol dispatch --role architecture.",
  "expected_outcome": "The CLI returns the architecture prompt.",
  "actual_outcome": "error: unknown dispatch role: architecture",
  "interpretation": "I treated the visible table label as the CLI slug.",
  "agent_name": "orchestrator",
  "agent_kind": "orchestrator",
  "anchors": [
    {"kind": "file", "path": "<skills-file-root>/SKILL.md", "line": 160}
  ]
}
EOF
```

WHEN JSON input is used THEN you SHOULD prefer stdin (`--from-json -`) over temp files.
WHEN payload text contains shell-sensitive content such as backticks, `$()`, copied command output, or multiple lines THEN you SHOULD prefer stdin JSON even if direct flags would otherwise work.
WHEN `--agent`, `--agent-kind`, or `--role` are omitted THEN the tool SHALL record provenance as unspecified instead of guessing.

WHEN `--from-json` parsing fails THEN the tool SHALL emit concise parser diagnostics without a raw stack trace.
WHEN the active runtime exposes line/column details THEN the tool SHOULD include them.

WHEN category selection is uncertain THEN you SHOULD let the categorizer choose the closest `surface/mode/run_effect` and keep the uncertainty in `Interpretation`.

WHEN overriding classification axes THEN you SHALL use only the values defined in `references/taxonomy.md`.

## Anchors

The event schema supports a generic `anchors` array so references are not limited to code.

Anchor fields may include:

- `kind`
- `path`
- `line`
- `end_line`
- `symbol`
- `section`
- `url`
- `selector`
- `label`

Use anchors when the friction references a file, function, document section, URL, or UI target that should be preserved for later review.

## Querying

Use the query script to filter the canonical event stream:

```sh
sh <skills-file-root>/scripts/query-friction.sh --category instructions/missing/blocked --format md
sh <skills-file-root>/scripts/query-friction.sh --date-from 2026-03-01 --date-to 2026-03-31 --format json
sh <skills-file-root>/scripts/query-friction.sh --anchor-path "<skills-file-root>/SKILL.md"
```

```powershell
& .\scripts\query-friction.ps1 -Category instructions/missing/blocked -Format md
& .\scripts\query-friction.ps1 -DateFrom 2026-03-01 -DateTo 2026-03-31 -Format json
& .\scripts\query-friction.ps1 -AnchorPath "$PWD\skills\friction-diagnostics\SKILL.md"
```

WHEN you need a custom slice that `query-friction.*` does not expose directly THEN you MAY read `events.jsonl` with `jq`.

Examples:

```sh
jq '.title' <repo>/.local/context/friction/events.jsonl
jq -s 'group_by(.fingerprint) | map({fingerprint: .[0].fingerprint, count: length})' <repo>/.local/context/friction/events.jsonl
```

WHEN reading prior friction THEN you SHOULD start with `INDEX.md`, then use `query-friction.*`, and only then read raw `events.jsonl` if you need a custom view.

## Definition of done

WHEN friction was encountered during a task THEN you SHALL leave behind:

- a canonical `events.jsonl`
- substantive entries with instruction source, action, expected outcome, actual outcome, and interpretation
- optional anchors when they help localize the issue
- an automatically maintained `INDEX.md`
- no fix proposals inside event payloads

WHEN no friction was encountered THEN the tool SHALL NOT create a friction event.
