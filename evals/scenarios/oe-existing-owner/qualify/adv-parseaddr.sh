# Adversarial (must fail invites_agree and calls_existing_validator): invite checks the address with email.utils.parseaddr.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-parseaddr
