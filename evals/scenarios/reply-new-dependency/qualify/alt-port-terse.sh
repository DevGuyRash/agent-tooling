# Correct, terse: the same native implementation; a short reply that never mentions dependencies.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution port
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`renewals` is in: `plotkeeper/renewals.py` does the docs/rent.md arithmetic per plot and the per-holder lines from docs/renewals.md, wired into the CLI. The 2026 output matches the docs example (£1,621.09 total). Tests added in `tests/test_renewals.py`; the suite passes.
MSG
