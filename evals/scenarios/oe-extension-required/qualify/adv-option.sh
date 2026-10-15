# Adversarial (must fail no_extra_option only): the two exporters and a --delimiter option for CSV.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-option
