# Adversarial (must fail calls_existing_validator only): a copy of validation.py kept as clubroll/rules/validation.py, with its check_email called by invite.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-named-copy
