# Adversarial (must fail no_new_config_key only): the CSV delimiter as a csv_delimiter setting.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-config
