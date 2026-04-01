# friction-diagnostics

`friction-diagnostics` records friction as a rolling structured event stream.

The canonical persisted file is:

- repo default: `<repo>/.local/reports/friction/events.jsonl`
- repo fallback when `.local` is absent: `<repo>/.local*/reports/friction/events.jsonl`
- fallback outside git: `<system-temp>/agent-friction/<cwd-hash>/events.jsonl`
- explicit override: `--events-file <path>`

`INDEX.md` lives next to `events.jsonl`, but it is fully tool-managed. Agents do not create or maintain it directly.

## Design choices

### 1. One canonical file

Everything meaningful is stored in `events.jsonl`.

- no `SESSION.txt`
- no `TASK_SUMMARY.txt`
- no `task.json`
- no descriptors
- no per-agent markdown logs
- no default `incidents.json`
- no default `exports/`

`INDEX.md` is the only default derived file kept on disk.

### 2. Filing path is heuristic-driven

Use direct flags only for short, single-line, scalar payloads with one source and no shell-sensitive text. Use stdin JSON for backticks, `$()`, copied command output, multiline text, or multiple `sources`. The `report-friction-json.*` helpers are thin wrappers around the safe JSON path when the caller does not want to hand-assemble the final `--from-json` command.

The simple direct-flags workflow is:

```sh
sh scripts/report-friction.sh \
  --title "Dispatch role slug mismatch" \
  --source-type file \
  --source-ref "SKILL.md" \
  --source-line 160 \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt." \
  --action-taken "Ran mpcr protocol dispatch --role architecture." \
  --expected-outcome "The CLI returns the architecture prompt." \
  --actual-outcome "error: unknown dispatch role: architecture" \
  --interpretation "I treated the visible table label as the CLI slug."
```

`--from-json PATH|-` remains available for compatibility and integrations. If JSON is used, prefer stdin over temp files. Also prefer stdin JSON whenever the payload contains shell-sensitive text such as backticks, `$()`, copied command output, or multiple lines.

Provenance is optional. If `--agent` or `--role` are omitted, the tool records provenance as unspecified instead of guessing.

PowerShell stdin example:

```powershell
@'
{"title":"Dispatch role slug mismatch","instruction_text":"Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt.","action_taken":"Ran mpcr protocol dispatch --role architecture.","expected_outcome":"The CLI returns the architecture prompt.","actual_outcome":"error: unknown dispatch role: architecture","interpretation":"I treated the visible table label as the CLI slug.","sources":[{"type":"file","ref":"SKILL.md","line":160}]}
'@ | & .\scripts\report-friction.ps1 -FromJson -
```

POSIX helper example:

```sh
cat <<'EOF' | sh scripts/report-friction-json.sh
{"title":"Complex payload","instruction_text":"Example","action_taken":"Example action taken with shell-sensitive text like `ghost-router` and $(whoami).","expected_outcome":"Example","actual_outcome":"Example","reading":"Example reading text that is long enough to satisfy validation.","hindsight":"Example hindsight text that is also long enough.","sources":[{"type":"documentation","ref":"test"}]}
EOF
```

### 3. Always-on write-time sanitization

The tool redacts common secrets and tokens before writing event text to disk. This keeps the hot append path deterministic while still protecting the stored event stream.

## Included files

- `SKILL.md` — usage guidance
- `scripts/report-friction.*` — append one event
- `scripts/query-friction.*` — query the canonical event stream
- `scripts/generate-report.*` — generate enhanced index, cross-repo, per-repo, and timeseries reports
- `scripts/build-index.*` — tool-managed index regeneration
- `scripts/categorize.*` — taxonomy heuristics
- `scripts/render-table.*` — render Unicode box-drawing tables from TSV/CSV/JSON-family input
- `scripts/render-summary.*` — render session summaries with query footer and source flattening
- `scripts/report-friction-json.*` — thin helpers that route JSON payloads into the safe `--from-json` filing path
- `references/` — integration and logging references
- `tests/` — smoke tests

## JSON input diagnostics

When `--from-json` is used:

- syntax failures return concise parser diagnostics, including line/column details when the active runtime exposes them
- invalid stdin JSON is saved under repo-local `.local/tmp/friction-diagnostics/` for replay when inside a git repo; outside a repo it falls back to the system temp directory
- schema failures return concise field-level errors
- raw parser stack traces are suppressed

## Querying

POSIX query, report, and index commands use `jq`. PowerShell variants use native object processing. The write path keeps Python only for advanced `--from-json` parsing and `--add-tags` rewriting.

Use `query-friction.*` to read `events.jsonl` directly:

```sh
sh scripts/query-friction.sh --category instructions/missing/blocked --format md
sh scripts/query-friction.sh --surface skill --run-effect blocked --date-from 2026-03-01
sh scripts/query-friction.sh --tag dispatch --text slug --format json
sh scripts/query-friction.sh --date-from 2026-03-01 --date-to 2026-03-31 --format json
sh scripts/query-friction.sh --source-ref "$PWD/skills/friction-diagnostics/SKILL.md"
```

```powershell
& .\scripts\query-friction.ps1 -Category instructions/missing/blocked -Format md
& .\scripts\query-friction.ps1 -Surface skill -RunEffect blocked -DateFrom 2026-03-01
& .\scripts\query-friction.ps1 -DateFrom 2026-03-01 -DateTo 2026-03-31 -Format json
& .\scripts\query-friction.ps1 -SourceRef "$PWD\skills\friction-diagnostics\SKILL.md"
```

Use `generate-report.*` for aggregate views:

```sh
sh scripts/generate-report.sh --events-file .local/reports/friction/events.jsonl --report-type index
sh scripts/generate-report.sh --scan-dirs ~/repos --report-type cross-repo
sh scripts/generate-report.sh --scan-dirs ~/repos --report-type timeseries --group-by surface
```

Recommended reading order:

1. Read `INDEX.md` for a compact summary.
2. Use `query-friction.*` for filtered views.
3. Use `generate-report.*` for aggregate views.
4. Drop to raw `events.jsonl` plus `jq` only when a custom slice is needed.

Session summary renderers are available on both POSIX and PowerShell:

```sh
sh scripts/render-summary.sh --events-file .local/reports/friction/events.jsonl --after 2026-04-01T12:00:00Z
```

```powershell
& .\scripts\render-summary.ps1 -EventsFile .local/reports/friction/events.jsonl -After 2026-04-01T12:00:00Z
```

## Notes

- There is no `init-log` step.
- `INDEX.md` is auto-created and auto-reconciled by the tooling after append operations.
- The canonical event schema supports a unified `sources` array so code and non-code references can be stored consistently.
- `--add-tags` uses the same file lock as event writes and swaps the updated JSONL into place atomically.
