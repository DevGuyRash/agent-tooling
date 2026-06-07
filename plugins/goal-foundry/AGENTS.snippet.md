# Goal Foundry working agreement

For long-running Codex work, do not launch `/goal` directly from vague intent or a backlog.

Use `$authoring-goals` first to create or validate one frozen `.goals/current.md` contract. A launchable goal must include terminal state, verifier, budget, scope edges, give-up conditions, and completeness dimensions. `.goals/GOALS.md` is a registry, not execution scope.

During an active `/goal` run, treat `.goals/current.md` and `.goals/current.sha256` as read-only. The executor may write only `.goals/evidence/` and `.goals/reports/` inside `.goals/` unless the user explicitly restarts authoring and re-locks the contract.
