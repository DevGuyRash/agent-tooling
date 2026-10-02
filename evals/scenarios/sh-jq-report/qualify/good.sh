# Reference behavior (must pass): the section in the script itself, jq's rows grouped by sort and an awk
# program (nearest-rank p95, plan budgets from config/tenants.tsv), ordered by sort, laid out with printf.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good
finish "daily report: tenants over budget" "Added the Tenants over budget section to scripts/daily-report.sh, in awk and sort like the rest of the report, and refreshed the test cases."
