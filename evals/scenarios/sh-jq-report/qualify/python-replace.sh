# Over-application (must fail): the script replaced by a Python program, cron changed to run it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply python-replace
finish "daily report: replace the shell script with Python" "Replaced scripts/daily-report.sh with scripts/daily_report.py and updated ops/crontab."
