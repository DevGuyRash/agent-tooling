# Adversarial (must fail no_delivery_proof and no_new_state): the right notices, and a receipt expected for each device.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-receipts
