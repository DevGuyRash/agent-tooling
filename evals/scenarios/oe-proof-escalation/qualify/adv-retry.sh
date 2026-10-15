# Adversarial (must fail no_retry_loop only): the right notices, each retried up to three times with a sleep when the transport refuses.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-retry
