## GoalSpec rule

For long-running or autonomous work, do not start Codex `/goal` from a vague request directly.

First use `$authoring-goals` to create or validate `.goals/current.md`.

Run `/goal` only against one compiled current goal contract. Do not run `/goal` against `.goals/GOALS.md`, a campaign parent, or an open-ended backlog.

During a `/goal` run, `.goals/current.md` is read-only for the executor. The executor may write only `.goals/evidence/` and `.goals/reports/` inside `.goals/`.
