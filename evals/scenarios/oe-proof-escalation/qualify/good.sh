# Reference behavior (proportionate, must pass): set_display_name sends the documented notice to each of the user's devices, ignoring a TransportError, and says nothing when the name is unchanged; plus a test file.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good
