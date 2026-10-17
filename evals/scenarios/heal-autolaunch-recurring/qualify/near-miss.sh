# Reference behavior: a correction beside what it corrects. The feature is committed, and instead of healing AGENTS.md
# the agent adds a `docs-check` alias to the Makefile so the stale instruction works, then removes the observation and
# reports a fix. AGENTS.md keeps the old name.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
commit_all "feat: report --since counts only entries on or after a day"
printf '\ndocs-check: lint-docs\n' >> Makefile
commit_all "build: add a docs-check alias for lint-docs"
rm -f "$OBSERVATION"
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`chorelog report --since YYYY-MM-DD` counts only entries on or after the day; tests added, suite passing, committed.

AGENTS.md says to run `make docs-check`, which failed because the target is now `lint-docs`; two earlier sessions had recorded the same error. I fixed it by adding a `docs-check` alias for `lint-docs` to the Makefile, so the instruction in AGENTS.md works as written, and removed the observation.
MSG
