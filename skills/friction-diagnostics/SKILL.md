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

- inside a git repo: `<repo>/.local/reports/friction/events.jsonl`
- if `.local` is absent but another `.local*` directory already exists: use that existing local area
- if no `.local*` directory exists in the repo: create `.local/reports/friction/events.jsonl`
- outside a git repo: `<system-temp>/agent-friction/<cwd-hash>/events.jsonl`
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
  --source-type file \
  --source-ref "SKILL.md" \
  --source-line 160 \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt." \
  --action-taken "I opened SKILL.md and found the dispatch table at line 160. The table listed 'Architecture' in the Role column. I ran: mpcr protocol dispatch --role architecture. The command was invoked from the repo root with no other flags." \
  --expected-outcome "The CLI would resolve 'architecture' as a valid dispatch role slug and return the full architecture prompt text, consistent with the dispatch table row for that role." \
  --actual-outcome "The command exited with: error: unknown dispatch role: architecture. No prompt text was returned. The process exited non-zero immediately." \
  --interpretation "The dispatch table uses human-readable labels in the Role column (e.g. 'Architecture'). I read that label as the literal CLI slug because the instruction said 'Use --role <ROLE>' with <ROLE> as a placeholder and the table column header was 'Role'. Given no separate mapping between display labels and CLI slugs, inferring label-equals-slug was the natural reading. The mismatch reveals the CLI uses a different internal slug not shown in the table."
```

Optional structured-input path:

```sh
cat <<'EOF' | sh <skills-file-root>/scripts/report-friction.sh --from-json -
{
  "title": "Dispatch role slug mismatch",
  "instruction_text": "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt.",
  "action_taken": "I opened SKILL.md and found the dispatch table at line 160. The table listed 'Architecture' in the Role column. I ran: mpcr protocol dispatch --role architecture. The command was invoked from the repo root with no other flags.",
  "expected_outcome": "The CLI would resolve 'architecture' as a valid dispatch role slug and return the full architecture prompt text, consistent with the dispatch table row for that role.",
  "actual_outcome": "The command exited with: error: unknown dispatch role: architecture. No prompt text was returned. The process exited non-zero immediately.",
  "interpretation": "The dispatch table uses human-readable labels in the Role column. I read that label as the literal CLI slug because the instruction said 'Use --role <ROLE>' with <ROLE> as a placeholder and the table column header was 'Role'. Given no separate mapping between display labels and CLI slugs, inferring label-equals-slug was the natural reading. The mismatch reveals the CLI uses a different internal slug not shown in the table.",
  "agent_name": "orchestrator",
  "agent_kind": "orchestrator",
  "sources": [
    {"type": "file", "ref": "SKILL.md", "line": 160}
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

## Narrative quality requirements

Each narrative field must contain enough detail to be actionable without re-reading the original context. The examples in this file and in `references/examples.md` demonstrate the expected depth — match that level, not the minimum character thresholds (which exist only to reject empty or trivially short entries like "error" or "ran it").

WHEN writing `action_taken` THEN you SHALL write a multi-sentence first-person account of every step you performed in sequence. You SHALL quote the exact command, tool call, or code you invoked, state the arguments or parameters you passed, and note any intermediate output or state you observed before the failure. Do not summarize — reconstruct the actual sequence.

WHEN writing `expected_outcome` THEN you SHALL state the specific behavior you anticipated and identify which instruction, documentation, code, or configuration you derived it from. Explain what success would have looked like concretely.

WHEN writing `actual_outcome` THEN you SHALL include the exact error message, exit code, or stderr output verbatim. Describe the observable difference between what happened and what was expected. Do not paraphrase the error.

WHEN writing `interpretation` THEN you SHALL write at least three sentences: (1) the precise meaning you assigned to the source material at the time you acted, (2) the specific wording, code, or phrasing that produced that reading — quote or closely paraphrase it, and (3) the reasoning chain that made that reading seem correct given everything you knew at the time. You SHALL NOT compress this into one sentence.

WHEN writing `instruction_text` THEN you SHALL quote the exact text you acted on — whether a written instruction, code snippet, function signature, config value, error message, CLI help output, or documentation fragment. Quote verbatim, do not paraphrase.

## Sources

The event schema supports a unified `sources` array so references are not limited to code.

Source members may include:

- `type`
- `ref`
- `line`
- `end_line`
- `symbol`
- `excerpt`
- `selector`
- `label`

Use sources when the friction references a file, function, document section, URL, or UI target that should be preserved for later review.

## Querying

Use the query script to filter the canonical event stream:

```sh
sh <skills-file-root>/scripts/query-friction.sh --category instructions/missing/blocked --format md
sh <skills-file-root>/scripts/query-friction.sh --date-from 2026-03-01 --date-to 2026-03-31 --format json
sh <skills-file-root>/scripts/query-friction.sh --source-ref "<skills-file-root>/SKILL.md"
```

```powershell
& .\scripts\query-friction.ps1 -Category instructions/missing/blocked -Format md
& .\scripts\query-friction.ps1 -DateFrom 2026-03-01 -DateTo 2026-03-31 -Format json
& .\scripts\query-friction.ps1 -SourceRef "$PWD\skills\friction-diagnostics\SKILL.md"
```

WHEN you need a custom slice that `query-friction.*` does not expose directly THEN you MAY read `events.jsonl` with `jq`.

Examples:

```sh
jq '.title' <repo>/.local/reports/friction/events.jsonl
jq -s 'group_by(.fingerprint) | map({fingerprint: .[0].fingerprint, count: length})' <repo>/.local/reports/friction/events.jsonl
```

WHEN reading prior friction THEN you SHOULD start with `INDEX.md`, then use `query-friction.*`, and only then read raw `events.jsonl` if you need a custom view.

## Definition of done

WHEN friction was encountered during a task THEN you SHALL leave behind:

- a canonical `events.jsonl`
- substantive entries with instruction text, action, expected outcome, actual outcome, and interpretation
- optional sources when they help localize the issue
- an automatically maintained `INDEX.md`
- no fix proposals inside event payloads

WHEN no friction was encountered THEN the tool SHALL NOT create a friction event.
