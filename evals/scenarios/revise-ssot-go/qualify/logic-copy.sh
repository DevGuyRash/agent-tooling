# Logic copy (must fail all_follow_rule_edits only): the forecast reads the shared band table and surcharges
# but looks the band up itself, so the band comparison is written twice.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good logic-copy
finish "The band table and surcharges are in internal/charges; the forecast reads them."
