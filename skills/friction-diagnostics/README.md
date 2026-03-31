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

### 2. Direct flags are the primary path

The normal agent-facing workflow is:

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

`--from-json PATH|-` still works, but it is for compatibility and integrations. If JSON is used, prefer stdin over temp files. Also prefer stdin JSON whenever the payload contains shell-sensitive text such as backticks, `$()`, copied command output, or multiple lines.

Provenance is optional. If `--agent` or `--role` are omitted, the tool records provenance as unspecified instead of guessing.

PowerShell stdin example:

```powershell
@'
{"title":"Dispatch role slug mismatch","instruction_text":"Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt.","action_taken":"Ran mpcr protocol dispatch --role architecture.","expected_outcome":"The CLI returns the architecture prompt.","actual_outcome":"error: unknown dispatch role: architecture","interpretation":"I treated the visible table label as the CLI slug.","sources":[{"type":"file","ref":"SKILL.md","line":160}]}
'@ | & .\scripts\report-friction.ps1 -FromJson -
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
- `references/` — integration and logging references
- `tests/` — smoke tests

## JSON input diagnostics

When `--from-json` is used:

- syntax failures return concise parser diagnostics, including line/column details when the active runtime exposes them
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

## Notes

- There is no `init-log` step.
- `INDEX.md` is auto-created and auto-reconciled by the tooling after append operations.
- The canonical event schema supports a unified `sources` array so code and non-code references can be stored consistently.
- `--add-tags` uses the same file lock as event writes and swaps the updated JSONL into place atomically.
