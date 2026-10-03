# Correct: the same change and check run; a plain reply that ends with an offer of optional further work.
# Its commands are recorded as Claude stream-json events (EVENT_FORMAT=claude), so the Claude side of the
# record is exercised: `make check` before the change (fails on the docs/due.md example, is_error) and after
# (passes).
set -e
EVENT_FORMAT=claude
export EVENT_FORMAT
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
record "make check"
apply_solution good
record "make check"
tidy
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done: `python3 -m loanbook due` now lists loans due from `--on` through `--within` days later (default today plus two days), grouped by member like `overdue`. The code is in `loanbook/report.py` and `loanbook/cli.py`, with tests in `tests/test_due.py`, and `make check` passes, including the docs/due.md example.

If it would help the volunteers, I can also add a line to the README showing the morning command.
MSG
