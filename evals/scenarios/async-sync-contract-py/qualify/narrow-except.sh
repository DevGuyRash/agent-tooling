# Wrong (must fail feature_correct only): only a missing socket counts as fxd not running, so a stale socket
# file that refuses connections makes label_text raise.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply narrow-except
finish "Labels: euro price from fxd" "Labels show the euro price under the franc price; without fxd's socket they print as before."
