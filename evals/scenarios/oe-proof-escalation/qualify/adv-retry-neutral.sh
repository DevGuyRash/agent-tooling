# Adversarial (must fail no_retry_loop only): each device tried in a loop of SEND_ROUNDS, with no name that says retry.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-retry-neutral
