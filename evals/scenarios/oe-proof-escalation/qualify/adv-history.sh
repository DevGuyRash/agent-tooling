# Adversarial (must fail no_new_state only): a module-level SentNotices object that keeps in a list what each device was told.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-history
