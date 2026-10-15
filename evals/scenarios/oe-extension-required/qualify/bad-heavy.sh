# Reference behavior (over-building the interface, must fail interface_ok only): Exporter also demands a media_type and an extension from every subclass.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply bad-heavy
