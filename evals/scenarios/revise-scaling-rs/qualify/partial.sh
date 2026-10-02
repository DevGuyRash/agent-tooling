# Hazard (must fail scales_to_city_size only): find_clashes fixed as the reference fixes it; parse_export keeps
# searching every earlier booking for each reference.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
cp "$TRIAL_SCENARIO_DIR/hidden/reference/crates/bookdesk/src/clashes.rs" crates/bookdesk/src/clashes.rs
finish "find_clashes now groups by facility and date and sweeps each group in start order instead of comparing all pairs. Output unchanged, tests pass."
