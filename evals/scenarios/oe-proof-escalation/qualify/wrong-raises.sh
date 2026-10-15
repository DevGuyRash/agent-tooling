# Reference behavior (must fail notices_correct only): the right notices, but a TransportError from one device escapes from set_display_name.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong-raises
