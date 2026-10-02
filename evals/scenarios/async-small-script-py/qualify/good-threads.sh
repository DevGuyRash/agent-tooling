# Reference behavior (must pass, over-built): the same report, each boat summarized in a thread pool sized to
# the CPUs. Correct; the measures show it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-threads
finish "boat_hours.py: time on the water per boat, service due" "Added scripts/boat_hours.py; boats are summarized in parallel in a thread pool."
