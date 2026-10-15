# Reference behavior (a variation that must pass): the command prints the CSV text with print(), which leaves a blank line at the end of the output.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-print
