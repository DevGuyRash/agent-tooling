# Reference behavior (must pass): the section without awk or jq, from sort, uniq, grep, cut, and sed, with one pass
# of a loop per tenant; the shell's steps stay a few hundred.
set -eu
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-coreutils
finish "daily report: tenants over budget" "Added the Tenants over budget section with sort, uniq, and sed."
