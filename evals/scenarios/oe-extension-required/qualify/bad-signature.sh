# Reference behavior (under-building, must fail interface_ok only): Exporter.export(self, report, settings), not the signature the user gave.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply bad-signature
