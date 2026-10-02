# Reference behavior (must pass, over-built): the same report from an asyncio script: the log read with
# asyncio.to_thread and each boat summarized as its own task under gather. Correct; the measures show it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-async
finish "boat_hours.py: time on the water per boat, service due" "Added scripts/boat_hours.py; it reads the log without blocking the event loop and summarizes the boats concurrently."
