# Integration patterns

## Paste-ready `AGENTS.md` snippet

```markdown
## Friction diagnostics
WHEN any error, failure, unexpected outcome, code bug, test failure, compilation error, runtime exception, or friction of any kind occurs THEN you SHALL immediately log it using the `friction-diagnostics` skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT create a duplicate entry.
WHEN friction is logged THEN you SHALL use the canonical repo-scoped `events.jsonl` target unless an explicit `--events-file` path is required.
WHEN the friction can be localized to a specific file, document, or URL THEN you SHALL populate the `sources` array in the event.
```

## Agent-facing default

Agents should use a filing-path heuristic. Filing the event is step 1; tagging is step 2.

- Use direct flags for short, single-line, scalar payloads with one source and no shell-sensitive text.
- Use `--from-json -` or the `report-friction-json.*` helper for backticks, `$()`, copied command output, multiline text, or multiple `sources`.

Step 1 — file the event:

```sh
sh scripts/report-friction.sh \
  --title "Referenced CI check script does not exist" \
  --source-type file \
  --source-ref "AGENTS.md" \
  --source-line 18 \
  --instruction-text "Run scripts/ci-check.sh to see the current build status." \
  --action-taken "I read AGENTS.md line 18 which directed me to run scripts/ci-check.sh. I searched for the file using rg --files scripts, which returned no match. I also checked for alternate names (ci_check.sh, check-ci.sh) and found none." \
  --expected-outcome "The scripts/ directory would contain ci-check.sh as an executable helper, consistent with the instruction's use of a bare concrete path in imperative form." \
  --actual-outcome "rg --files scripts returned no match for ci-check.sh or any variant. The file is completely absent from the repository." \
  --reading "The instruction at line 18 uses a concrete path in imperative form: 'Run scripts/ci-check.sh'. There is no conditional qualifier or note about generating the script first. Imperative instructions with literal paths refer to existing artifacts, so I treated it as a pre-existing helper. Its absence is a documentation gap."
```

Step 2 — the tool output shows existing tags and suggests the command. Run it:

```sh
sh scripts/report-friction.sh --add-tags evt-NNNN "missing-script,instructions"
```

## Structured-input path

`--from-json` is the recommended safe path for complex payloads. If JSON is used, prefer stdin:

```sh
cat <<'EOF' | sh scripts/report-friction.sh --from-json -
{
  "title": "Referenced CI check script does not exist",
  "instruction_text": "Run scripts/ci-check.sh to see the current build status.",
  "action_taken": "I read AGENTS.md line 18 which directed me to run scripts/ci-check.sh. I searched for the file using rg --files scripts, which returned no match. I also checked for alternate names (ci_check.sh, check-ci.sh) and found none.",
  "expected_outcome": "The scripts/ directory would contain ci-check.sh as an executable helper, consistent with the instruction's use of a bare concrete path in imperative form.",
  "actual_outcome": "rg --files scripts returned no match for ci-check.sh or any variant. The file is completely absent from the repository.",
  "reading": "The instruction at line 18 uses a concrete path in imperative form: 'Run scripts/ci-check.sh'. There is no conditional qualifier or note about generating the script first. Imperative instructions with literal paths refer to existing artifacts, so I treated it as a pre-existing helper. Its absence is a documentation gap.",
  "agent_name": "orchestrator",
  "sources": [
    {"type": "file", "ref": "AGENTS.md", "line": 18}
  ]
}
EOF
```

Use stdin JSON whenever the payload contains backticks, `$()`, copied command output, or multiple lines that would be brittle as inline shell arguments.
The `agent_name` field in the example above is explicit provenance supplied by the caller, not a default that the tool invents.
The JSON payload does not include a `tags` field. Events are written with an empty tags array. After filing, run the suggested `--add-tags` command shown in the tool output.

Helper examples:

```sh
cat <<'EOF' | sh scripts/report-friction-json.sh
{
  "title": "Complex payload through helper",
  "instruction_text": "Use the safe JSON helper when payload text is shell-sensitive.",
  "action_taken": "I piped a JSON payload with backticks and dollar-paren text through report-friction-json.sh instead of hand-quoting direct flags.",
  "expected_outcome": "The helper would forward the JSON payload into the safe --from-json path.",
  "actual_outcome": "The payload was filed successfully without shell expansion damage.",
  "reading": "The helper removes manual shell quoting from the complex-payload path while preserving the same event schema and validation behavior.",
  "hindsight": "Use the helper whenever the payload would be annoying or risky to express as inline flags.",
  "sources": [
    {"type": "documentation", "ref": "test"}
  ]
}
EOF
```

## Canonical target resolution

When `--events-file` is omitted, `report-friction.*` resolves the canonical file this way:

1. repo-local `.local/reports/friction/events.jsonl`
2. if `.local` is absent, first existing repo-local `.local*/reports/friction/events.jsonl`
3. if no `.local*` directory exists, create `.local/reports/friction/events.jsonl`
4. outside git, fall back to a deterministic system-temp path

This means subagents and nested subagents in the same repo converge on the same rolling file without session IDs or parent IDs.

## Index behavior

`INDEX.md` is adjacent to `events.jsonl`, but it is fully tool-managed:

- the tool creates it automatically when needed
- the tool updates it automatically after append operations
- agents do not run a separate create or rebuild step in the normal workflow

## Querying

POSIX query, report, and index commands use `jq`. PowerShell variants use native object processing. The write path keeps Python only for advanced `--from-json` parsing and `--add-tags` rewriting.

Use the query script to filter the canonical event stream:

```sh
sh scripts/query-friction.sh --category instructions/missing/blocked --format md
sh scripts/query-friction.sh --surface skill --run-effect blocked --date-from 2026-03-01
sh scripts/query-friction.sh --tag dispatch --text slug --format json
sh scripts/query-friction.sh --source-ref "$PWD/skills/friction-diagnostics/SKILL.md"
```

```powershell
& .\scripts\query-friction.ps1 -Category instructions/missing/blocked -Format md
& .\scripts\query-friction.ps1 -Surface skill -RunEffect blocked -DateFrom 2026-03-01
& .\scripts\query-friction.ps1 -SourceRef "$PWD\skills\friction-diagnostics\SKILL.md"
```

Use the report generator for aggregate views:

```sh
sh scripts/generate-report.sh --events-file .local/reports/friction/events.jsonl --report-type index
sh scripts/generate-report.sh --scan-dirs ~/repos --report-type cross-repo
sh scripts/generate-report.sh --scan-dirs ~/repos --report-type timeseries --group-by surface
```

If an agent needs an ad hoc parse beyond the built-in query filters, it can read the raw stream with `jq`:

```sh
jq '.title' .local/reports/friction/events.jsonl
jq -s 'map(select(.role == "research"))' .local/reports/friction/events.jsonl
```

Practical read flow:

1. inspect `INDEX.md`
2. query with `query-friction.*`
3. use `generate-report.*` for aggregate views
4. use raw `events.jsonl` plus `jq` for custom analysis
