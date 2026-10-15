# Reference behavior (realistic over-building, must fail): the interface and both exporters, plus a @register_exporter registry, entry-point plugin loading, a third (TSV) exporter, a --delimiter option, and a default_format setting.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply bad-over
