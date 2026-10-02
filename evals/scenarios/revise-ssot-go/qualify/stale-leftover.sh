# Leftover (must fail one_rule_definition only): the good solution, with the forecast's old band table and
# surcharges left in forecast.go, unused.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good stale-leftover
finish "Moved the charges to internal/charges and pointed all three commands at it."
