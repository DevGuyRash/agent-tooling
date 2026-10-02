# Partial (must fail all_follow_rule_edits and one_rule_definition): the quote and the renewal letters share
# internal/charges; the forecast keeps its own copy, updated and fixed.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good partial
finish "The quote and the letters share internal/charges; the forecast's table is updated to match."
