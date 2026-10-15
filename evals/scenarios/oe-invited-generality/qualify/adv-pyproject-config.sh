# Adversarial (must fail no_new_config_key only): the delimiter read with tomllib from [tool.stallbook] in pyproject.toml.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-pyproject-config
