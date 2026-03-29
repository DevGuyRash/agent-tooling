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

A rolling event stream that captures friction — errors, failures, mismatches, and unexpected outcomes — as structured JSONL.

WHEN any error, failure, unexpected outcome, or friction occurs THEN you SHALL log it using this skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT add a duplicate entry.

The canonical data is `events.jsonl`. `INDEX.md` is an auto-maintained summary.

---

## How to file

Filing a friction event requires two commands. The event is not complete until both have run.

1. **`report-friction.sh`** — writes the event and outputs the event ID + existing tags
2. **`report-friction.sh --add-tags`** — tags the event using the ID from command 1

### Command 1 — report

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

WHEN payload text contains shell-sensitive content such as backticks, `$()`, or multiple lines THEN you SHOULD use `--from-json -` via stdin instead of direct flags. See `references/examples.md` for the JSON format.

WHEN `--agent`, `--agent-kind`, or `--role` are omitted THEN the tool records provenance as unspecified rather than guessing.

### Command 2 — tag

The output from command 1 includes the event ID, existing tags in the stream, and the exact `--add-tags` invocation to run. Run it.

```sh
sh <skills-file-root>/scripts/report-friction.sh --add-tags evt-NNNN "skill,name-resolution,dispatch,mpcr"
```

WHEN choosing tags THEN you SHALL select relevant tags from the existing vocabulary shown AND create new tags for dimensions not yet covered — tool name, language, component, failure pattern, domain. More tags are better than fewer.

---

## Narrative depth

`references/examples.md` shows bad-vs-good comparisons for every field. Read it before filing your first event.

Summary of what each field requires:

- **`action_taken`** — three sentences: (1) what you read or consulted before acting and where, (2) the exact command or code you executed with arguments, (3) what you observed before and during the failure.
- **`interpretation`** — three sentences: (1) the meaning you assigned to the source material — use single-quotes to quote the specific wording verbatim, (2) why that reading was reasonable given context, (3) what the mismatch reveals about the source, the environment, or your assumption. Sentence (3) is a diagnostic observation, not an action plan — do not write what to do next.
- **`actual_outcome`** — the exact error message, exit code, or output verbatim. Do not paraphrase.
- **`expected_outcome`** — the specific behavior you anticipated and which source you derived it from.
- **`instruction_text`** — the exact text you acted on, quoted verbatim.

Do not propose fixes, next steps, or corrective actions inside event payloads. Phrases like "the correct fix is", "the safer correction is", "the correct next step is", or "the right approach is" belong in your working context, not in the friction record.

WHEN no error, failure, or unexpected outcome has occurred yet THEN you SHALL NOT log a friction event. Task starts, delegation handoffs, and in-progress status are not friction.

---

## How to query

Start with `INDEX.md` for an overview. Use the query script for filtered views. Fall back to raw `events.jsonl` with `jq` for custom slices.

```sh
sh <skills-file-root>/scripts/query-friction.sh --category instructions/missing/blocked --format md
sh <skills-file-root>/scripts/query-friction.sh --source-ref "SKILL.md"
```

---

## Reference

### Canonical storage

- Inside a git repo: `<repo>/.local/reports/friction/events.jsonl`
- If `.local` absent but `.local*` exists: use that existing local area
- No `.local*` in the repo: create `.local/reports/friction/events.jsonl`
- Outside git: `<system-temp>/agent-friction/<cwd-hash>/events.jsonl`
- Explicit override: `--events-file <path>`

`INDEX.md` is auto-maintained next to `events.jsonl`. Agents do not create or rebuild it.

### Scripts

| Script | Purpose |
|---|---|
| `report-friction.sh` / `.ps1` | Append one event; `--add-tags` to tag after |
| `query-friction.sh` / `.ps1` | Filter and render the event stream |
| `categorize.sh` / `.ps1` | Classify an event as `surface/mode/run_effect` |
| `build-index.sh` / `.ps1` | Internal index maintenance |

No `init-log` step required.

### Sources

The `sources` array accepts typed references — not limited to code:

| Field | Description |
|---|---|
| `type` | `file`, `url`, `system-instruction`, `conversation`, `audio`, `visual`, `documentation`, `other` |
| `ref` | Primary reference: filepath, URL, or description |
| `line`, `end_line` | Line range (for files) |
| `symbol` | Function, class, section, or heading name |
| `excerpt` | Relevant quoted text from the source |
| `selector` | CSS selector, XPath, section anchor, timestamp |
| `label` | Human-readable description of this source's role |

### Classification

The categorizer auto-detects `surface`, `mode`, `run_effect`, `confidence` (1–5), and `guidance_quality` (0–4). Override any axis with explicit flags when the heuristic is wrong. Use only values from `references/taxonomy.md`. WHEN the source material's ambiguity or incompleteness contributed to the friction THEN you SHOULD set `guidance_quality` below 4 to reflect that. A value of 4 means "clear" — use it only when the guidance was genuinely unambiguous and the friction came from elsewhere.

WHEN category selection is uncertain THEN you SHOULD let the categorizer choose and note the uncertainty in `interpretation`.
