# Reference behavior (must fail csv_cases_pass and json_cases_pass only): both exporters write the revenue as a float.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong
