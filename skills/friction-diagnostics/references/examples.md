# Examples

## Good event

```sh
sh scripts/report-friction.sh \
  --agent subagent-a \
  --agent-kind subagent \
  --role research \
  --title "Missing CI helper" \
  --source-type file \
  --source-ref "AGENTS.md" \
  --source-line 18 \
  --instruction-text "Run scripts/ci-check.sh to inspect current status." \
  --action-taken "I read AGENTS.md and found the instruction at line 18 directing me to run scripts/ci-check.sh. I attempted to locate the file using rg --files scripts, which listed every file under scripts/. The file ci-check.sh was not present in the listing. I also checked for alternate names (ci_check.sh, check-ci.sh) and found none." \
  --expected-outcome "The scripts/ directory would contain ci-check.sh, executable and ready to run, consistent with the instruction's use of a bare concrete path without any caveat about the file being optional or conditional." \
  --actual-outcome "rg --files scripts returned no match for ci-check.sh or any variant. The file is completely absent from the repository." \
  --interpretation "The instruction at line 18 uses a concrete, unqualified path in imperative form: 'Run scripts/ci-check.sh'. There is no conditional qualifier, no 'if it exists', and no note that the script must be generated first. Imperative instructions with literal paths normally refer to existing artifacts, so I treated this as a pre-existing helper I was expected to invoke. The script's absence reveals either a documentation gap or a setup step that was meant to precede this instruction."
```

Why it is good:

- localizes the friction to a specific file and line via `--source-type` and `--source-ref`
- `action_taken` reconstructs the full investigation sequence, not just the final conclusion
- `expected_outcome` explains what success would have looked like and why
- `actual_outcome` includes the exact command output, not a paraphrase
- `interpretation` quotes the specific language ("Run scripts/ci-check.sh"), explains the reading, and provides reasoning for why that reading was natural

## Bad event (shallow but technically complete)

```sh
sh scripts/report-friction.sh \
  --title "CI script failed" \
  --source-type documentation \
  --source-ref "AGENTS.md" \
  --instruction-text "Run the CI check script to see current status." \
  --action-taken "Ran the script and it was not there." \
  --expected-outcome "It would work." \
  --actual-outcome "Got an error about the file not existing." \
  --interpretation "The instructions seemed wrong about the script path."
```

Why it is bad:

- `action_taken` does not quote the exact command, arguments, or output — "Ran the script" could mean anything
- `expected_outcome` gives no basis for the expectation — what instruction was it derived from? What would success look like concretely?
- `actual_outcome` omits the exact error message — "Got an error" has no diagnostic value
- `interpretation` gives no quoted language from the instruction and no reasoning chain — it is a conclusion without a trace
- `instruction_text` paraphrases instead of quoting the exact text
- all fields technically have content but none is recoverable for diagnosis without returning to the original context

## Good JSON via stdin

```sh
cat <<'EOF' | sh scripts/report-friction.sh --from-json -
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

The `agent_name` and `agent_kind` fields above are explicit provenance provided by the caller, not defaults inferred by the tool.
