# Reference behavior (realistic escalation, must fail): the display-name notice goes through send_critical, widened to take extra fields and retry: signed, audited, receipted, with a retry loop and sleeps, and a last_notified_name on the user.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply bad
