# Wrong (must fail hidden_cases_correct): fast like the reference, but the duplicate key leaves out the fare,
# so two taps that differ only in fare count as one. The fixture's tests do not cover that difference; the
# hidden duplicates case and every generated day do, so it also fails scales_to_network_size on its output.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference" "$Q/solutions/wrong-key"
finish "charge is one pass now: duplicates are found with a Set keyed on time, card, route and stop, and the per-card state and debits are kept in Maps. Tests pass."
