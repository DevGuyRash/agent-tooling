# Adversarial (must fail no_new_state only): the right notices, and a _last_notified dict on Accounts remembering what each device was told.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-memo
