- Live-verify on Claude: boundary presence lines at session start in a repo with open events; filing right after a resume stamps the CURRENT session id (sidecar); `pgrep -af zsh` shows no duplicate FRICTION\_ export growth.
- Live-verify on Codex: the ported SessionStart hook fires; note whether hook stdout enters context (boundary lines are best-effort there); filing under `codex exec` still stamps CODEX_THREAD_ID.
- Trigger boundary probes (`evals/trigger-prompts.json` in both skills) still need a formal skill-surfacing eval run per harness.
- The mend half has never run end-to-end on a real corpus (345 anchors across 7 repos, 0 published trap files); the first real mend session is the outstanding validation experiment, user-invoked.
- After 2-4 weeks of v5.2 data, review `generate-report.sh --report-type stats` against the v4 baseline (targets: noisy+continued <40%; pivot_information and decision top-5 trigram share <25% with high distinct-openers, vs 94% hindsight baseline; recurrence records >0; key collisions ~0; ≥1 resolution filed; ≥1 session observed avoiding a known trap).

Plugin errors nobody has fixed. `just audit-plugins --errors-only` is the live list; delete an entry here when it is fixed:

- Some `excel-foundry` launchers still lack the executable bit.
- `goalspec` and `playwright-testing` catalog versions disagree with their manifests; goalspec's catalog description still describes the pre-decision-funnel design.
- No LICENSE file sits behind the MIT declaration every manifest carries.

CI audits only the plugins a change touches, so these block nobody until someone edits the plugin that owns them.

Active risks:

- GoalSpec V4 still needs a live decision-funnel gauntlet across Codex and Claude before claiming behavioral success; grade design clarity, convergence quality, artifact restraint, probe quality, default handling, and product regressions.
- Confirm the Windows event-stream lock timeout (`FRICTION_LOCK_TIMEOUT`, ownerless-lock reclaim) the next time that stream is exercised, then drop this line.
- Excel Foundry cloud commands still need opt-in live Graph/Fabric/Power BI validation with tenant env vars and safe test resources before any cloud surface is promoted to supported.
- Claude `agents/*.md` surfaces are reported as `preserved_only` in claude→codex conversion but have no Codex mapping; decide whether a Codex-side agent equivalent should exist or whether preserved-only is the end state.
- Skill-auditor 2.0.0 has produced exactly one Improvement Brief, written and graded by the same context that built the skill. Nobody independent has judged whether the brief is good, and there is no baseline against what 1.0.0 would have said for the same target. Treat the outcome as demonstrated once, not validated.

Software-development v1 release acceptance remains incomplete:

- Claude model-backed trigger and no-plugin task-quality evals require an authenticated Claude session; this machine is not logged in.
- Representative no-plugin baseline comparisons and unavailable PowerShell/Swift/Kotlin runtime matrix checks remain release gates before publishing.
