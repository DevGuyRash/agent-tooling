# Resolved to a copy (must fail drift_resolved, and all_follow_rule_edits): one shared package, but with the
# forecast's exclusive band comparison.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good wrong-drift
finish "The charges now live in internal/charges with the 2027/28 changes."
