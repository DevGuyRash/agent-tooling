# Over-application (must fail): the section moved into a new Python program the script launches.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply python-section
finish "daily report: tenants over budget" "Added the Tenants over budget section; the per-tenant percentiles are in scripts/tenants_over_budget.py, which the report runs."
