# Examples

## Good event

```sh
sh scripts/report-friction.sh \
  --agent subagent-a \
  --agent-kind subagent \
  --role research \
  --title "Missing CI helper" \
  --instruction-source "AGENTS.md:18" \
  --instruction-text "Run scripts/ci-check.sh to inspect current status." \
  --action-taken "Ran rg --files scripts and confirmed ci-check.sh does not exist." \
  --expected-outcome "The repository contains scripts/ci-check.sh." \
  --actual-outcome "No such script exists in the repository." \
  --interpretation "The instruction used a concrete script path in imperative form, so I understood it as pointing to an existing helper." \
  --anchor-kind file \
  --anchor-path "$PWD/AGENTS.md" \
  --anchor-line 18
```

Why it is good:

- records the exact instruction source
- preserves what the agent did
- distinguishes expected vs actual outcome
- includes an interpretation grounded in the wording
- adds an anchor that localizes the source

## Bad event

```text
Tool broken. Please fix.
```

Why it is bad:

- no instruction source
- no action taken
- no expected outcome
- no actual outcome
- no interpretation

## Good JSON via stdin

```sh
cat <<'EOF' | sh scripts/report-friction.sh --from-json -
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
    {"kind": "file", "path": "/abs/path/SKILL.md", "line": 160}
  ]
}
EOF
```

The `agent_name` and `agent_kind` fields above are explicit provenance provided by the caller, not defaults inferred by the tool.

PowerShell variant for shell-sensitive JSON:

```powershell
@'
{"title":"Dispatch role slug mismatch","instruction_source":"SKILL.md:160","instruction_text":"Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt.","action_taken":"Ran mpcr protocol dispatch --role architecture.","expected_outcome":"The CLI returns the architecture prompt.","actual_outcome":"error: unknown dispatch role: architecture","interpretation":"I treated the visible table label as the CLI slug.","role":"lead"}
'@ | & .\scripts\report-friction.ps1 -FromJson -
```
