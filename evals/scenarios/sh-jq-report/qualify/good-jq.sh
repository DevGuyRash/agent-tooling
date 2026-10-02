# Must pass: the grouping and p95 in a jq filter over the log, the budgets and layout in awk.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-jq
finish "daily report: tenants over budget" "Added the Tenants over budget section (jq groups, awk lays out)."
