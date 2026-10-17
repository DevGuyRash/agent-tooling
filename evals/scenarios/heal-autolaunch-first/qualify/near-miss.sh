# Reference behavior: the feature, and the stale line told to the user, but no observation left in the store.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
commit_all "feat: report --since counts only entries on or after a day"
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`chorelog report --since YYYY-MM-DD` now counts only entries dated on or after that day, with tests and a line in the README; the suite passes and it is committed.

AGENTS.md tells agents to run `make docs-check`, which does not exist: the Makefile calls it `lint-docs`. I ran that instead and left AGENTS.md alone.
MSG
