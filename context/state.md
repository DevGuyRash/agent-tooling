Active risks:

- GoalSpec 1.1.0 (autonomous campaign chains, `656b78f`) is merged to local main but not on origin — main is 1 commit ahead and the commit exists only on this machine. Push, then `scripts/install-all --include goalspec` to deploy; all sessions until then run pre-1.1.0 hooks/scripts from the caches.
- GoalSpec LF-3 still open: the first real-task run end-to-end, now best done as a real campaign chain (authoring agent produces the manifest + children, owner pastes the rendered `--campaign` `/goal`). The chain is the least field-tested load-bearing feature; every e2e so far was a synthetic subagent.
- Codex PreToolUse open question (evt-0174): confirm whether it can fire at all under `approval_policy = never` + danger-full-access — until then the contract/campaign freeze on Codex is detect-only (audit catches, nothing prevents).
- GoalSpec doctrine candidate for the next SKILL.md touch: prefer independent reviewer-agent gates over human gates for subjective verifiers (full hands-off by default); reserve human gates for explicit owner veto. Also: watch whether hand-authored provenance drift (evt-0178/0179) recurs in LF-3 before adding any nudge.
- Friction diagnostics helper is hanging on this Windows event stream; do not leave stale `.report-friction.lock` behind after attempts to log.
- Excel Foundry cloud commands still need opt-in live Graph/Fabric/Power BI validation with tenant env vars and safe test resources before any cloud surface is promoted to supported.
- Claude `agents/*.md` surfaces are now reported as `preserved_only` in claude→codex conversion but still have no Codex mapping; decide whether a Codex-side agent equivalent should exist or whether preserved-only is the end state.
