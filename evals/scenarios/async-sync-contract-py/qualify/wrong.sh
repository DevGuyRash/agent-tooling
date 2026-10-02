# Wrong (must fail feature_correct only): the price divided by the rate instead of multiplied.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong
finish "Labels: euro price from fxd" "Labels show the euro price under the franc price."
