# Reference behavior (must fail notices_correct only): the notice goes to the first device only, without the previous name.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong
