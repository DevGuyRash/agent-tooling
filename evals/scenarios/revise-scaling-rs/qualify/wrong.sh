# Wrong (must fail hidden_cases_correct): fast, but each booking is compared only with the longest-running
# earlier booking of its group, which misses a clash with a shorter booking still running. The fixture's sample
# week has no such case; the hidden three-way overlaps do.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference" "$Q/solutions/wrong-sweep"
finish "Clashes are found per facility and date in start order, comparing each booking with the one running longest; repeated references use a HashMap. Tests pass."
