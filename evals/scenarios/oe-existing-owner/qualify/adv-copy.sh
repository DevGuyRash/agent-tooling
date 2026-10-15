# Adversarial (must fail calls_existing_validator only): invite carries its own copy of every rule, the disposable list included, and agrees with check_email on every input.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-copy
