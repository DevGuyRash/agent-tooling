# Reference behavior: the accepted outcome, except that the feature and its tests are left in the working tree.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
leave_observation
report 'The `report --since YYYY-MM-DD` option now counts only entries dated on or after that day, with tests and a line in the README; the suite passes. The feature is in the working tree and not committed.'
