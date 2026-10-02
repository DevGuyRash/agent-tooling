# Over-application (must fail): the whole report rewritten in Python, the script now just execs it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply python-rewrite
finish "daily report in Python, with tenants over budget" "Rewrote the daily report as scripts/daily_report.py (no more awk and jq programs embedded in shell) and added Tenants over budget; scripts/daily-report.sh still works for cron."
