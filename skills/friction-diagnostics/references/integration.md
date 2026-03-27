# Integration patterns

## Paste-ready `AGENTS.md` snippet

```markdown
## Friction diagnostics
WHEN any error, failure, unexpected outcome, code bug, test failure, compilation error, runtime exception, or friction of any kind occurs THEN you SHALL immediately log it using the `friction-diagnostics` skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT create a duplicate entry.
WHEN friction is logged THEN you SHALL use the canonical repo-scoped `events.jsonl` target unless an explicit `--events-file` path is required.
```

## Agent-facing default

Agents should use direct flags by default:

```sh
sh scripts/report-friction.sh \
  --title "Referenced CI check script does not exist" \
  --instruction-source "AGENTS.md:18" \
  --instruction-text "Run scripts/ci-check.sh to see the current build status." \
  --action-taken "Ran rg --files scripts and confirmed ci-check.sh does not exist." \
  --expected-outcome "The repository contains scripts/ci-check.sh." \
  --actual-outcome "The file does not exist in the repository." \
  --interpretation "The instruction used a concrete script path in imperative form, so I understood it as pointing to an existing helper."
```

## Structured-input path

`--from-json` remains supported, but it is not the recommended default. If JSON is used, prefer stdin:

```sh
cat <<'EOF' | sh scripts/report-friction.sh --from-json -
{
  "title": "Referenced CI check script does not exist",
  "instruction_source": "AGENTS.md:18",
  "instruction_text": "Run scripts/ci-check.sh to see the current build status.",
  "action_taken": "Ran rg --files scripts and confirmed ci-check.sh does not exist.",
  "expected_outcome": "The repository contains scripts/ci-check.sh.",
  "actual_outcome": "The file does not exist in the repository.",
  "interpretation": "The instruction used a concrete script path in imperative form, so I understood it as pointing to an existing helper.",
  "agent_name": "orchestrator",
  "agent_kind": "orchestrator"
}
EOF
```

Use stdin JSON whenever the payload contains backticks, `$()`, copied command output, or multiple lines that would be brittle as inline shell arguments.
The `agent_name` and `agent_kind` fields in the example above are explicit provenance supplied by the caller, not defaults that the tool invents.

## Canonical target resolution

When `--events-file` is omitted, `report-friction.*` resolves the canonical file this way:

1. repo-local `.local/context/friction/events.jsonl`
2. first existing repo-local `.local*/context/friction/events.jsonl`
3. create `.local/context/friction/events.jsonl`
4. outside git, fall back to a deterministic temp-root path

This means subagents and nested subagents in the same repo converge on the same rolling file without session IDs or parent IDs.

## Index behavior

`INDEX.md` is adjacent to `events.jsonl`, but it is fully tool-managed:

- the tool creates it automatically when needed
- the tool updates it automatically after append operations
- agents do not run a separate create or rebuild step in the normal workflow

## Querying

Use the query script to filter the canonical event stream:

```sh
sh scripts/query-friction.sh --category instructions/missing/blocked --format md
sh scripts/query-friction.sh --agent-kind subagent --format json
sh scripts/query-friction.sh --anchor-path "$PWD/skills/friction-diagnostics/SKILL.md"
```

```powershell
& .\scripts\query-friction.ps1 -Category instructions/missing/blocked -Format md
& .\scripts\query-friction.ps1 -AgentKind subagent -Format json
& .\scripts\query-friction.ps1 -AnchorPath "$PWD\skills\friction-diagnostics\SKILL.md"
```

If an agent needs an ad hoc parse beyond the built-in query filters, it can read the raw stream with `jq`:

```sh
jq '.title' .local/context/friction/events.jsonl
jq -s 'map(select(.agent_kind == "subagent"))' .local/context/friction/events.jsonl
```

Practical read flow:

1. inspect `INDEX.md`
2. query with `query-friction.*`
3. use raw `events.jsonl` plus `jq` for custom analysis
