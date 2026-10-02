# Hazard (must fail scales_to_network_size only): the three searches stay, made cheap per step: typed arrays
# of times and card numbers, no arrays or callbacks per tap, searches from the newest entry back. Several
# times faster than the old code and identical in output, still quadratic.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/micro-opt"
finish "Sped up the hot loops in dropDuplicates, chargeDay and cardDebits: they now scan typed arrays of times and card numbers instead of building filtered arrays for every tap. Output unchanged, tests pass."
