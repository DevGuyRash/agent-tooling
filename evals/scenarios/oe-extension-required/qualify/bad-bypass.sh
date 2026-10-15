# Reference behavior (under-building, must fail via_interface only): Exporter, CsvExporter and JsonExporter exist, and cli.py ignores them and calls render_csv and render_json.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply bad-bypass
