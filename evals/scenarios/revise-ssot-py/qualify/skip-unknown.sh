# Over-reach (must fail existing_behavior_kept only): good, but the overnight notices skip a loan of a category
# the policy does not know and the kiosk charges it nothing, where the fixture refuses the export in both.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good skip-unknown
finish "The fines rule now lives in circdesk/fines.py and all three commands use it; the notices and the kiosk no longer stop on an unknown category."
