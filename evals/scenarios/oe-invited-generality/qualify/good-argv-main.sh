# Reference behavior (a variation that must pass): __main__.py passes sys.argv[1:] to main.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-argv-main
