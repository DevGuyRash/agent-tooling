# Hazard (must fail scales_to_city_size only): parse_export fixed as the reference fixes it; find_clashes keeps
# the pairwise loop, made cheap per pair (facility codes normalized once up front, the cheap tests first).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference" "$Q/solutions/micro-opt"
finish "Removed the allocations from the clash loop (facility codes are normalized once, not twice per pair) and the reference lookup now uses a HashMap. Output unchanged, tests pass."
