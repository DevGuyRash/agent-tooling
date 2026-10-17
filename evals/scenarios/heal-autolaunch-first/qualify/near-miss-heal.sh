# Reference behavior: the observation is left, and AGENTS.md is healed as well, at the first occurrence.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
commit_all "feat: report --since counts only entries on or after a day"
leave_observation
correct_agents
commit_agents
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`chorelog report --since YYYY-MM-DD` now counts only entries dated on or after that day, with tests in tests/test_report.py and tests/test_cli.py and a line in the README; the suite passes and it is committed.

AGENTS.md told agents to run `make docs-check`, which does not exist: the Makefile calls it `lint-docs`. I left an observation about it in `.local/observations/` and corrected AGENTS.md to say `make lint-docs` (committed as `docs: AGENTS.md names the lint-docs target`).
MSG
