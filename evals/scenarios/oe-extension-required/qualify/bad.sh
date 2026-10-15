# Reference behavior (under-building, must fail interface_ok and via_interface only): CSV and JSON as render_csv and render_json functions, no Exporter.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply bad
