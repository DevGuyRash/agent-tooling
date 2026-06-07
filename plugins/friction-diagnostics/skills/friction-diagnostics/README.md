# friction-diagnostics

`friction-diagnostics` records friction as a rolling structured event stream. It is a cognitive debugging tool for agent behavior — capturing WHY an agent made decisions and where reasoning diverged from reality.

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

`INDEX.md` is the only default derived file kept on disk.

### 2. Filing is a single command

Use direct flags for short, single-line, scalar payloads with one source and no shell-sensitive text. Use stdin JSON for backticks, `$()`, multiline text, or multiple sources.

```sh
sh scripts/report-friction.sh \
  --title "Dispatch role slug mismatch" \
  --source-type file \
  --source-ref "SKILL.md" \
  --source-line 160 \
  --source-excerpt "Use mpcr protocol dispatch --role <ROLE>." \
  --expected-outcome "The CLI returns the architecture prompt." \
  --actual-outcome "error: unknown dispatch role: architecture" \
  --reading "The dispatch table had 'Architecture' in the Role column. I plugged in 'architecture' as the CLI slug. The CLI rejected it — the actual slug is 'architecture-critic', which doesn't appear anywhere in the table." \
  --hindsight "I should have run --list-roles first instead of inferring from a display table." \
  --impact blocked \
  --tags "dispatch,slug-mismatch,mpcr" \
  --aliases "instructions"
```

JSON stdin example:

```sh
cat <<'EOF' | sh scripts/report-friction.sh --from-json -
{
  "title": "SSH signing agent unavailable",
  "expected_outcome": "Git would create the commit object.",
  "actual_outcome": "error: 1Password: Could not connect to socket.",
  "reading": "The commit failed during signing because SSH_AUTH_SOCK had no socket available.",
  "impact": "blocked",
  "tags": ["ssh-auth-sock", "git-signing"],
  "aliases": ["auth", "git"],
  "sources": [
    {"type": "file", "ref": "functions.exec_command", "excerpt": "git commit -m 'docs: add skill'"}
  ]
}
EOF
```

Post-hoc tag/alias additions remain available:

```sh
sh scripts/report-friction.sh --add-tags evt-NNNN "new-tag1,new-tag2"
sh scripts/report-friction.sh --add-aliases evt-NNNN "broader-group"
```

### 3. Always-on write-time sanitization

The tool redacts common secrets and tokens before writing event text to disk.

## Included files

- `SKILL.md` — usage guidance
- `scripts/report-friction.sh` — append one event with tags, aliases, and impact inline
- `scripts/query-friction.sh` — query the canonical event stream
- `scripts/generate-report.sh` — generate index, cross-repo, per-repo, and timeseries reports
- `scripts/build-index.sh` — tool-managed index regeneration
- `scripts/render-table.sh` — render Unicode box-drawing tables
- `scripts/render-summary.sh` — render session summaries with query footer
- `scripts/report-friction-json.sh` — thin helper for the safe `--from-json` filing path
- `references/` — integration, logging spec, and examples
- `tests/` — smoke tests

## JSON input diagnostics

When `--from-json` is used:

- syntax failures return concise parser diagnostics with line/column details
- invalid stdin JSON is saved under repo-local `.local/tmp/friction-diagnostics/` for replay
- schema failures return concise field-level errors
- raw parser stack traces are suppressed

## Querying

```sh
sh scripts/query-friction.sh --impact blocked --format md
sh scripts/query-friction.sh --tag auth --date-from 2026-03-01
sh scripts/query-friction.sh --alias environment --format json
sh scripts/query-friction.sh --source-ref "SKILL.md"
sh scripts/generate-report.sh --scan-dirs ~/repos --report-type cross-repo
```

Tag queries use substring matching: `--tag auth` matches tags containing "auth" (e.g., `ssh-auth-sock`). Use `--tag-exact` for exact matches. Same for `--alias` / `--alias-exact`.

Recommended reading order:

1. Read `INDEX.md` for a compact summary.
2. Use `query-friction.*` for filtered views.
3. Use `generate-report.*` for aggregate views.
4. Drop to raw `events.jsonl` plus `jq` only when a custom slice is needed.

Session summary renderers:

```sh
sh scripts/render-summary.sh --events-file .local/reports/friction/events.jsonl --after 2026-04-01T12:00:00Z
```

## Notes

- There is no `init-log` step.
- `INDEX.md` is auto-created and auto-reconciled by the tooling after append operations.
- The canonical event schema supports a unified `sources` array so code and non-code references can be stored consistently.
- `--add-tags` and `--add-aliases` use the same file lock as event writes and swap the updated JSONL into place atomically.
