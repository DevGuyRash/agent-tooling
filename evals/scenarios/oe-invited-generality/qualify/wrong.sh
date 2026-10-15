# Reference behavior (must fail csv_cases_pass only): a CSV with unformatted revenue, a totals line, and the default line ending.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong
