# Adversarial (must fail no_extra_format only): CSV, and JSON as well.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-format
