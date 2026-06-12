# Renderer Rules for Codex /goal

The rendered `/goal` objective should be compact but verifier-complete.

## Source of truth

`.goals/current.md` is the source of truth. The `/goal` text points to it and summarizes non-droppable clauses.

The render binds outcomes, scope, budget, and oracles — never method. Any execution path that satisfies them is valid; the executing agent owns the how exactly as the authoring agent does.

## Do not drop

- terminal-state clauses
- verifier requirements
- scope edges
- budget
- give-up conditions
- evidence requirements
- follow-up policy
- contract freeze rule

## May shorten

- intent
- long context
- detailed capability inventory
- examples
- commentary

## Template

```text
/goal Complete the frozen goal contract in .goals/current.md. First read that file and treat it as the source of truth. The task is complete only when all terminal-state clauses are satisfied, the verifier requirements pass or are reported unavailable, scope edges are respected, the budget and give-up conditions are honored, and required evidence is written to the final report. Do not treat .goals/GOALS.md as execution scope. Do not modify .goals/current.md or .goals/current.sha256 during execution. Write only .goals/evidence/ and .goals/reports/ inside .goals/. Stop and report blocked/incomplete if the verifier cannot run, the budget is exhausted, or satisfying the goal requires out-of-scope changes. Final report must include files changed, commands run, raw results or artifact paths, budget used, risks, and follow-up candidates.
```

## Campaign chain render

Rendering a locked campaign writes the frozen chain runtime to `.goals/bin/`
(`campaign_status.py`, `run_verifiers.py`, `audit_goal.py`, `common.py`,
`select_goal.py`, raw-byte hashes in `MANIFEST.sha256`) and the chain text
invokes those workspace-local copies — the mission survives plugin upgrades
that prune old cache versions. Re-rendering overwrites `.goals/bin/` (that is
the recovery path); the executor never writes it, and the audit warns when a
vendored file no longer matches its recorded hash.

The chain text is durable across threads by construction: it never names a
starting child; the executor derives `next_child` from `campaign_status.py`
each time, skips achieved children, pauses at attestation-only children until
their report records the gate outcome, and stops when the status tool says
stop. The same rendered line stays correct for the whole campaign lifecycle.

## Pointer mode (prompt-length-limited targets)

`render_goal.py --pointer` writes the full render to `.goals/rendered-goal.md` (or `.goals/rendered-campaign.md` for `--campaign`) and prints one short launch line carrying two hashes: the mission hash (contract sha256 / campaign aggregate sha256) and the pointer file's own sha256. The executor reads the pointer file first — the file, not the line, carries the projection, and `.goals/current.md` stays the source of truth over both. WHEN either hash does not match at launch THEN you SHALL stop and report contract mutated.

Rendered files are byte-exact payloads, not editable documents: exempt `.goals/rendered-*.md` from markdown formatters (e.g. via `.prettierignore`) or expect to re-render after any rewrite — a formatter edit breaks the launch line's file hash loudly, by design.
