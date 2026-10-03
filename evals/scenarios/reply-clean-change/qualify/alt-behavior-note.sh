# Correct: the same change and check run; a plain reply with a factual note on behavior the spec defines.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution good
record "make check"
tidy
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the `due` command from docs/due.md (`loanbook/report.py`, `loanbook/cli.py`, tests in `tests/test_due.py`). `make check` passes.

As the spec says, both ends of the range count, so on a Saturday the default (`--within 2`) covers Saturday through Monday, and loans already past their due date stay on the `overdue` list rather than this one.
MSG
