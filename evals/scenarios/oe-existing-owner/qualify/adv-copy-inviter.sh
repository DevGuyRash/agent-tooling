# Adversarial (must fail calls_existing_validator only): invite carries its own copy of every rule for the address and asks check_email only about the inviter.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-copy-inviter
