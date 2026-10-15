# Adversarial (must fail no_new_state and no_retry_loop): the right notices, and a module-level queue.Queue of the refused ones with a drain() that sends them again in a loop.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-outbox
