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
compatibility: Designed for filesystem-capable coding agents on Linux. Deterministic helpers require POSIX sh. No network required.
metadata:
  author: generated-template
  version: "4.0.0"
  category: diagnostics
  tags: friction,logging,postmortem,troubleshooting
---

# Friction Diagnostics

A cognitive debugging tool for agent behavior. Captures friction — errors, failures, mismatches, and unexpected outcomes — as structured JSONL, with emphasis on tracing the agent's reasoning chain so that instructions and environments can be improved.

WHEN any error, failure, unexpected outcome, or friction occurs THEN you SHALL log it using this skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT add a duplicate entry.
WHEN you are about to file an event THEN you SHALL check the last 5 entries in the events stream (via the query tool or `tail -5`). WHEN an existing entry has the same title or describes the same root cause THEN you SHALL NOT file a new event.

The canonical data is `events.jsonl`. `INDEX.md` is an auto-maintained summary.

---

## How to file

Filing a friction event is a single command. Provide the narrative, sources, impact, and classification together.

Use this filing-path heuristic:

- Direct flags are for short, single-line, scalar payloads with one source and no shell-sensitive text.
- `--from-json -` is the safe path for backticks, `$()`, copied command output, multiline text, or multiple `sources`.

```sh
sh <skills-file-root>/scripts/report-friction.sh \
  --title "Git commit failed — SSH signing agent unavailable" \
  --source-type file \
  --source-ref "functions.exec_command" \
  --source-excerpt "git -C /path/to/repo commit -m 'docs: add skill'" \
  --expected-outcome "Git would create the commit object for the staged skill files." \
  --actual-outcome "error: 1Password: Could not connect to socket specified by SSH_AUTH_SOCK. fatal: failed to write commit object" \
  --reading "I had staged the files and passed the leak scan. I ran git commit and it failed during the signing phase because SSH_AUTH_SOCK had no socket available in this terminal session. The staging was clean so this was purely an environment issue. I retried with signing disabled for this one command." \
  --hindsight "I should have checked whether this repo enforces commit signing through an external agent before issuing the commit." \
  --impact blocked \
  --tags "ssh-auth-sock,git-signing,1password,commit" \
  --aliases "auth,git"
```

### Tags and aliases

**Tags** are specific, natural labels that describe what was involved: `ssh-auth-sock`, `git-signing`, `cargo-test`, `missing-file`. Use whatever words feel natural.

**Aliases** are broader groupings: `auth`, `git`, `environment`, `permissions`, `instructions`. They help cluster related events for INDEX summaries and cross-event queries.

Both are normalized to lowercase on write. You MAY provide both at filing time. The output shows existing tags and aliases in the stream for reference.

`--add-tags` and `--add-aliases` remain available for post-hoc additions:

```sh
sh <skills-file-root>/scripts/report-friction.sh --add-tags evt-NNNN "new-tag1,new-tag2"
sh <skills-file-root>/scripts/report-friction.sh --add-aliases evt-NNNN "broader-group"
```

### Impact

WHEN filing an event THEN you SHALL provide `--impact` with one of:

- **`blocked`** — work stopped; you could not proceed without a workaround or different approach
- **`degraded`** — work continued but with reduced quality, a workaround, or a fallback
- **`noisy`** — work continued but required extra retries, thrashing, or effort
- **`continued`** — friction was observed but did not disrupt the workflow

### Fingerprint

Fingerprints are computed from `source_ref|date`. Events from the same source on the same day share a fingerprint, enabling recurrence detection in the INDEX.

WHEN you want finer or different grouping THEN you SHOULD use `--fingerprint-key "descriptive key"` to override the default seed.

---

## Narrative depth

`references/examples.md` shows bad-vs-good comparisons for every field. Read it before filing your first event.

Summary of what each field requires:

- **`reading`** — first person. The core field. Your full account of what happened: what you consulted, what you did, what you observed, how you interpreted it, and why you made the decisions you made. Quote the specific wording you acted on. Vary your language — do not follow a sentence template. This is your story, not your analysis. A reader should understand your perspective, your decision points, and the moment things diverged. WHEN the source wording shaped your understanding THEN you SHALL quote it verbatim. You SHALL NOT use formulaic framing like "that reading was reasonable" or "the mismatch reveals."
- **`hindsight`** — first person. What you believe you should have done differently, knowing what you know now. This is about your decisions and approach, not about changes to the source material. WHEN you cannot identify anything you would do differently THEN you SHALL say so and explain why.
- **`actual_outcome`** — the exact error message, exit code, or output verbatim. Do not paraphrase.
- **`expected_outcome`** — the specific behavior you anticipated and which source you derived it from.

Do not propose fixes, next steps, or corrective actions inside event payloads. Those belong in your working context, not in the friction record.

WHEN no error, failure, or unexpected outcome has occurred yet THEN you SHALL NOT log a friction event. Task starts, delegation handoffs, and in-progress status are not friction.

---

## Sources

The `sources` array identifies where friction originated. Each entry points to a source the agent consulted or acted on.

Ask: **"What artifact contains the text, code, or config that broke or misled me?"**

| Field | Description |
|---|---|
| `type` | `file`, `url`, `conversation`, `audio`, `visual`, `documentation`, `other` |
| `ref` | Primary reference: filepath, URL, or description |
| `line`, `end_line` | Line range (for files) |
| `excerpt` | Verbatim quote from the source — the specific text you acted on |

WHEN friction originates from a file THEN `type` SHALL be `file` and `ref` SHALL be the file path.
WHEN friction is in what the user said (e.g., an ambiguous instruction with no backing artifact) THEN `type` SHALL be `conversation`.
WHEN text from multiple sources shaped the action THEN you SHALL use multiple entries in the `sources` array, each pointing to its own artifact.

---

## How to query

Start with `INDEX.md` for an overview. Use the query and report scripts for filtered views.

```sh
sh <skills-file-root>/scripts/query-friction.sh --impact blocked --format md
sh <skills-file-root>/scripts/query-friction.sh --tag auth --date-from 2026-03-01
sh <skills-file-root>/scripts/query-friction.sh --alias environment --format json
sh <skills-file-root>/scripts/query-friction.sh --source-ref "SKILL.md"
sh <skills-file-root>/scripts/generate-report.sh --scan-dirs ~/repos --report-type cross-repo
```

Tag queries use substring matching: `--tag auth` matches tags containing "auth" (e.g., `ssh-auth-sock`, `auth-failure`). Use `--tag-exact` for exact matches. Same for `--alias` / `--alias-exact`.

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
| `report-friction.sh` | Append one event with tags, aliases, and impact inline; `--add-tags` / `--add-aliases` for post-hoc additions |
| `query-friction.sh` | Filter and render the event stream by impact, tags, aliases, text, dates, and sources |
| `generate-report.sh` | Generate `index`, `cross-repo`, `per-repo`, or `timeseries` reports |
| `build-index.sh` | Internal index maintenance |

No `init-log` step required.

---

## Session summary

WHEN your task is complete AND you logged at least one new friction event since your last assistant turn THEN you SHALL include a friction summary at the end of your final response.

WHEN no new friction events were logged since your last assistant turn THEN you SHALL NOT render a summary.

### How to produce

Run the summary renderer and paste its output verbatim:

```sh
sh <skills-file-root>/scripts/render-summary.sh \
  --events-file <events-file> \
  --after "<last-turn-timestamp>"
```

The script produces a header, a table (with ID, Time, Title, Impact, Tags, and Sources columns), and a footer with the events file path and a ready-to-paste re-query command.

You SHALL NOT manually construct or format the table. Paste the script output as-is.

WHEN you do not have the last-turn timestamp THEN you SHALL use the most recent available lower bound that excludes already-reported events. IF no such lower bound is available THEN you SHALL use `--date-from` with today's date instead of `--after`.
