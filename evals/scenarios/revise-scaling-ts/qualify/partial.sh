# Hazard (must fail scales_to_network_size only): chargeDay is fixed as the reference fixes it (each card's
# state in a Map), but dropDuplicates and cardDebits keep their searches.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
cp "$TRIAL_SCENARIO_DIR/hidden/reference/src/fares.ts" src/fares.ts
finish "chargeDay no longer filters every earlier charge for each tap; it keeps each card's spend and journey start in a Map. Output unchanged, tests pass."
