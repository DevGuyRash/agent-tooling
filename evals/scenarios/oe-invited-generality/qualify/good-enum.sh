# Reference behavior (a variation that must pass): the formats as an enum used for the choices and the default of --format, with no __str__.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-enum
