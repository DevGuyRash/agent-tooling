# Adversarial (must fail no_new_config_key only): the two exporters and a json_indent setting.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-config
