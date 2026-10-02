# Over-application (must fail): the section in plain sh, its per-request work in while-read loops so that no awk or
# jq program does it; correct and still the shell script, but several shell steps per request.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply pure-sh
finish "daily report: tenants over budget" "Added the Tenants over budget section in plain sh."
