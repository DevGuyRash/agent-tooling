# Adversarial (must fail no_new_state only): the right notices, and a last_sent dict kept as a class attribute of Accounts.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-classattr
