# Adversarial (must fail no_new_config_key only): the CSV delimiter from an environment variable.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-env
