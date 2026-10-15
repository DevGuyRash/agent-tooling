# Reference behavior (a variation that must pass): Exporter carries a name string that subclasses set and the command line uses to pick one.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-name-attr
