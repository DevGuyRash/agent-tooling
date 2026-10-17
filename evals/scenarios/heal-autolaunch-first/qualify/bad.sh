# Reference behavior: a healing pass at the first occurrence. The feature is committed, then AGENTS.md is rewritten to
# name the target that exists, as if a pass had run, with no observation left and the reply reporting the fix.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
commit_all "feat: report --since counts only entries on or after a day"
correct_agents
commit_agents
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`chorelog report --since YYYY-MM-DD` counts only entries on or after the day; tests added, suite passing, committed.

AGENTS.md told agents to run `make docs-check`, which failed because the target is now `lint-docs`. I corrected AGENTS.md to say `make lint-docs` (committed as `docs: AGENTS.md names the lint-docs target`).
MSG
