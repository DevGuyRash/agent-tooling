# Examples

Read this file before filing your first friction event. It defines the expected depth for every field.

---

## Field-by-field: bad vs good

Each pair shows the same friction — a missing CI script referenced in AGENTS.md — reported at two quality levels.

### `action_taken`

Bad:
> Ran the script and it was not there.

Good:
> I read AGENTS.md and found the instruction at line 18 directing me to run scripts/ci-check.sh. I ran `rg --files scripts` to search for the file, which listed every entry under scripts/. ci-check.sh was not present. I also checked for alternate names (ci_check.sh, check-ci.sh) and found none.

Why the bad version fails: it doesn't say which script, what command was used to look for it, or what was observed. "Ran the script" is not reconstructable.

### `interpretation`

Bad:
> The instructions seemed wrong about the script path.

Good:
> The instruction at line 18 uses a concrete, unqualified path in imperative form: "Run scripts/ci-check.sh". There is no conditional qualifier, no "if it exists", and no note that the script must be generated first. Imperative instructions with literal paths normally refer to existing artifacts, so I treated this as a pre-existing helper. The script's absence reveals either a documentation gap or a missing setup step.

Why the bad version fails: it draws a conclusion ("seemed wrong") without quoting the source language, explaining the reading, or tracing the reasoning. It's a verdict, not an interpretation.

### `actual_outcome`

Bad:
> Got an error about the file not existing.

Good:
> rg --files scripts returned no match for ci-check.sh or any variant. The file is completely absent from the repository.

Why the bad version fails: "Got an error" has no diagnostic value. The good version includes the exact tool output so someone reading the event can understand the failure without re-running the command.

### `expected_outcome`

Bad:
> It would work.

Good:
> The scripts/ directory would contain ci-check.sh, executable and ready to run, consistent with the instruction's use of a bare concrete path without any caveat about the file being optional.

Why the bad version fails: "It would work" says nothing about what success looks like, what behavior was anticipated, or where that expectation came from.

### `instruction_text`

Bad:
> Run the CI check script to see current status.

Good:
> Run scripts/ci-check.sh to inspect current status.

Why the bad version fails: it paraphrases instead of quoting verbatim. "The CI check script" is the agent's summary, not the instruction's words.

---

## Complete good event (CLI flags)

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
  --action-taken "I read AGENTS.md and found the instruction at line 18 directing me to run scripts/ci-check.sh. I ran rg --files scripts to search for the file, which listed every entry under scripts/. ci-check.sh was not present. I also checked for alternate names (ci_check.sh, check-ci.sh) and found none." \
  --expected-outcome "The scripts/ directory would contain ci-check.sh, executable and ready to run, consistent with the instruction's use of a bare concrete path without any caveat about the file being optional or conditional." \
  --actual-outcome "rg --files scripts returned no match for ci-check.sh or any variant. The file is completely absent from the repository." \
  --interpretation "The instruction at line 18 uses a concrete, unqualified path in imperative form: 'Run scripts/ci-check.sh'. There is no conditional qualifier, no 'if it exists', and no note that the script must be generated first. Imperative instructions with literal paths normally refer to existing artifacts, so I treated this as a pre-existing helper. The script's absence reveals either a documentation gap or a setup step that was meant to precede this instruction."
```

Then tag it (step 2):

```sh
sh scripts/report-friction.sh --add-tags evt-NNNN "missing-script,instructions,ci,agents-md"
```

## Complete good event (JSON stdin)

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

The JSON payload has no `tags` field. Events start with an empty tags array. Run the `--add-tags` command from the tool output as step 2.
