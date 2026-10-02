# Must fail: the reference with the p95 rank taken as floor(0.95 n) instead of the ceiling.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong
finish "daily report: tenants over budget" "Added the Tenants over budget section."
