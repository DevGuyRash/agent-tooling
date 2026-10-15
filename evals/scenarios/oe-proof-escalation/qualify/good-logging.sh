# Reference behavior (a variation that must pass): a send_to_devices helper in notices.py that logs a refused device with its traceback, and set_display_name calling it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-logging
