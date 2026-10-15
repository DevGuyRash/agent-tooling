# Reference behavior (realistic over-engineering, must fail): an exporters module with an abstract Exporter, a decorator registry, text, CSV (delimiter and header options), and JSON exporters; --delimiter and --no-header; csv_delimiter and csv_header settings.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply bad
