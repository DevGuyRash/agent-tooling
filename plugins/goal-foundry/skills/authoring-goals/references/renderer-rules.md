# Renderer Rules for Codex /goal

The rendered `/goal` objective should be compact but verifier-complete.

## Source of truth

`.goals/current.md` is the source of truth. The `/goal` text points to it and summarizes non-droppable clauses.

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
