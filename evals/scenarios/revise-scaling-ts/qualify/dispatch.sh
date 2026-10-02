# Wrong behind a size switch (must fail scales_to_network_size only): the reference's chargeDay and cardDebits,
# and a dropDuplicates that keeps the old search up to 30k taps (the pilot, the tests, the generated 20k-tap
# case) and above that switches to a Set keyed without the fare, so on a network-size day two taps that differ
# only in fare count as one. Every generated day holds such near-twins, so the small and large scaling inputs
# show the difference; the hand-made cases are too small to reach the switch.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference" "$Q/solutions/dispatch-key"
finish "Small days keep the original duplicate check; full network days use a Set keyed on time, card, route and stop, and the per-card state and debits are kept in Maps. Tests pass."
