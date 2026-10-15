# Adversarial (must fail no_new_state only): the right notices, and an audit entry for each device.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-audit
