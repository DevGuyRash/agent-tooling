# Adversarial (must fail no_extra_option only): CSV with a --delimiter option.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-option
