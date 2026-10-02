# The behavior the shared qualify plan runs as bad (must fail): patch-only, every copy of the fines rule edited
# for the request and fixed to docs/fines.md, which passes every hidden case today and fails
# all_follow_rule_edits and one_rule_definition.
sh "$TRIAL_SCENARIO_DIR/qualify/patch-only.sh"
