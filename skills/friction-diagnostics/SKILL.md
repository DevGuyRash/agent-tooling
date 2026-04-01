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
WHEN you are about to file an event THEN you SHALL check the last 5 entries in the events stream (via the query tool or `tail -5`). WHEN an existing entry has the same title or describes the same root cause THEN you SHALL NOT file a new event.

The canonical data is `events.jsonl`. `INDEX.md` is an auto-maintained summary.

---

## How to file

Filing a friction event requires two commands. The event is not complete until both have run.

1. **`report-friction.sh`** — writes the event and outputs the event ID + existing tags
2. **`report-friction.sh --add-tags`** — tags the event using the ID from command 1

### Command 1 — report

Use this filing-path heuristic:

- Direct flags are for short, single-line, scalar payloads with one source and no shell-sensitive text.
- `--from-json -` is the safe path for backticks, `$()`, copied command output, multiline text, or multiple `sources`.
- `report-friction-json.sh` / `.ps1` are thin helpers for that safe path when you do not want to hand-assemble the final `--from-json` invocation.

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
  --reading "The dispatch table had a column called 'Role' with 'Architecture' in it, and the instruction said 'Use --role <ROLE>'. So I plugged in 'architecture' — the table column was labeled 'Role,' the placeholder said ROLE, seemed like a direct substitution. The CLI rejected it immediately: 'unknown dispatch role: architecture.' Turns out the actual slug is 'architecture-critic,' which doesn't appear anywhere in the table or the surrounding text." \
  --hindsight "I should have run the CLI's own discovery command first — something like --list or --help on the dispatch subcommand — instead of inferring the slug from a display table. The table uses human-friendly labels; the CLI uses internal slugs. Those are two different naming schemes and I treated them as one."
```

WHEN payload text contains shell-sensitive content such as backticks, `$()`, or multiple lines THEN you SHOULD use `--from-json -` via stdin instead of direct flags. See `references/examples.md` for the JSON format.

WHEN `--agent` or `--role` are omitted THEN the tool records provenance as unspecified rather than guessing.

### Fingerprint stability

Fingerprints are computed from `surface|mode|source_ref|date`. Narrative text does NOT affect the fingerprint. However, if the auto-categorizer assigns a different `surface` or `mode` for the same error (because wording varied), the fingerprint changes.

WHEN you encounter a recurring error pattern that you have logged before THEN you SHOULD provide `--surface` and `--mode` explicitly to lock the categorization and keep the fingerprint stable.

WHEN the auto-categorizer struggles with an error class (the same underlying issue gets different categories across events) THEN you SHOULD use `--fingerprint-key "descriptive key"` to override the default fingerprint seed entirely.

WHEN logging an error similar to a prior event in the stream THEN you SHOULD use consistent terminology in narrative fields (especially `actual_outcome` and `action_taken`) to help the categorizer's pattern matching produce stable results.

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
- **`reading`** — first person. Your account of what happened from your perspective: what you encountered, what you understood it to mean, what you did, and what surprised you. Quote the specific wording you acted on. Vary your language — do not follow a sentence template. This is your story, not your analysis. A reader should understand your perspective, your decision points, and the moment things diverged — without being told "this was reasonable" or "the mismatch reveals." WHEN the source wording shaped your understanding in a specific way THEN you SHALL quote it verbatim. You SHALL NOT use the phrases "that reading was reasonable," "the mismatch reveals," "the mismatch shows," or any formulaic framing. Narrate what happened to you.
- **`hindsight`** — first person. What you believe you should have done differently, knowing what you know now. This is about your decisions and approach, not about changes to the source material or codebase. WHEN you cannot identify anything you would do differently THEN you SHALL say so and explain why — the friction may have been unavoidable given what you knew.
- **`actual_outcome`** — the exact error message, exit code, or output verbatim. Do not paraphrase.
- **`expected_outcome`** — the specific behavior you anticipated and which source you derived it from.
- **`instruction_text`** — the exact text you acted on, quoted verbatim.

Do not propose fixes, next steps, or corrective actions inside event payloads. Phrases like "the correct fix is", "the safer correction is", "the correct next step is", or "the right approach is" belong in your working context, not in the friction record.

WHEN no error, failure, or unexpected outcome has occurred yet THEN you SHALL NOT log a friction event. Task starts, delegation handoffs, and in-progress status are not friction.

---

## How to query

Start with `INDEX.md` for an overview. Use the query and report scripts for filtered views.

POSIX query/report/index commands use `jq`. PowerShell variants use native object processing. The write path keeps Python only for advanced `--from-json` parsing and `--add-tags` rewriting.

```sh
sh <skills-file-root>/scripts/query-friction.sh --category instructions/missing/blocked --format md
sh <skills-file-root>/scripts/query-friction.sh --surface skill --run-effect blocked --date-from 2026-03-01
sh <skills-file-root>/scripts/query-friction.sh --source-ref "SKILL.md"
sh <skills-file-root>/scripts/generate-report.sh --scan-dirs ~/repos --report-type cross-repo
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
| `query-friction.sh` / `.ps1` | Filter and render the event stream with category dimensions, text, numeric ranges, and exact-match filters |
| `generate-report.sh` / `.ps1` | Generate `index`, `cross-repo`, `per-repo`, or `timeseries` reports |
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

The categorizer auto-detects `surface`, `mode`, `run_effect`, `confidence` (1–5), and `guidance_quality` (0–4). Override any axis with explicit flags when the heuristic is wrong. Use only values from `references/taxonomy.md`.

WHEN the source text could be read more than one way and you picked one THEN `guidance_quality` SHALL be 2 (ambiguous) or lower.
WHEN the source text was correct but omitted information you needed THEN `guidance_quality` SHALL be 3 (partial).
WHEN the source text actively pointed you toward the wrong action THEN `guidance_quality` SHALL be 1 (misleading).
WHEN no source text was involved (purely operational friction like a timeout, missing binary, or resource limit) THEN `guidance_quality` SHALL be 0 (not-applicable).
A value of 4 (clear) means you followed unambiguous, accurate guidance and the friction came from elsewhere entirely — the guidance did its job.

WHEN the automatic `mode` is `other` AND you can identify a more specific mode from the taxonomy THEN you SHALL override with `--mode <value>`. Common overrides: `apply_patch` or edit context mismatch → `output-mismatch`; spawn/thread/resource limit → `performance`; variable rejected as invalid, reserved, or unbound → `validation`.

WHEN category selection is uncertain THEN you SHOULD let the categorizer choose and note the uncertainty in `reading`.

---

## Session summary

WHEN your task is complete AND you logged at least one friction event during this session THEN you SHALL include a friction summary at the end of your final response.

WHEN no friction events were logged during the session THEN you SHALL NOT render a summary.

### How to produce

Run the summary renderer and paste its output verbatim. The script handles querying, source flattening, table formatting, and re-query footer generation.

```sh
sh <skills-file-root>/scripts/render-summary.sh \
  --events-file <events-file> \
  --after "<session-start-timestamp>"
```

```powershell
& <skills-file-root>\scripts\render-summary.ps1 `
  -EventsFile <events-file> `
  -After "<session-start-timestamp>"
```

WHEN you do not have the session start timestamp THEN you SHALL use `--date-from` with today's date instead of `--after`.

### Output layout

Place the full output of `render-summary.sh` or `render-summary.ps1` after all task content. The script produces a header, a Unicode box-drawing table (with ID, Time, Title, Category, Tags, and Sources columns), and a footer with the events file path and a ready-to-paste re-query command.

You SHALL NOT manually construct or format the table. Paste the script output as-is.

---

## Source attribution

The `source_type`, `source_ref`, and `instruction_text` fields identify where friction originates. Trace back to the artifact that contains the friction — not the channel that delivered the task.

### Decision heuristic

Ask: **"What artifact contains the text, code, or config that broke or misled me?"**

- `source_ref` → the artifact itself (file path, URL, MCP schema, API doc)
- `source_type` → what kind of artifact it is (use the existing enum: `file`, `url`, `documentation`, `system-instruction`, `conversation`, etc.)
- `instruction_text` → verbatim quote from the artifact identified in `source_ref`

This applies to any domain — skills, MCP servers, API docs, books, codebases — without enumerating each one.

### Rules

WHEN friction originates from a loaded skill's instructions or scripts THEN `source_type` SHALL be `file` and `source_ref` SHALL be the skill file path — not `conversation`.

WHEN the user's conversational instruction triggered the task but the friction is in an artifact THEN the source is the artifact, not the conversation. The conversation is the trigger, not the origin.

WHEN friction is genuinely in what the user said (e.g., an ambiguous user instruction with no backing artifact) THEN `source_type` SHALL be `conversation`.

WHEN text from multiple sources shaped the action THEN you SHALL use the `sources` array with multiple entries, each pointing to its own artifact. You SHALL NOT merge text from different sources into a single `instruction_text`.

`instruction_text` SHALL be a verbatim quote from the single source identified in `source_ref`. You SHALL NOT paraphrase, blend, or combine text from different origins.
