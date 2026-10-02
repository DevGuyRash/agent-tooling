# Resolved to a copy (must fail drift_resolved, and all_follow_rule_edits): one shared module, but the
# children's most taken from the receipt's copy (2.50) instead of docs/fines.md (3.00).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good wrong-drift
finish "The fines rule now lives in circdesk/fines.py, taken from the receipt, with the 1 November changes."
