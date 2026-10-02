# Reference behavior (must pass, no constructs): good, plus a docstring and a comment that explain in prose why
# the script is not async ("nothing to await, so no asyncio"; "A thread pool or asyncio.gather() per boat ...").
# The construct measures count syntax, not words, so it scores none.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
cp -R "$Q/solutions/good/." .  # its test too; apply lists the script in the README once
apply good-explained
finish "boat_hours.py: time on the water per boat, service due" "Added scripts/boat_hours.py: one sequential pass over the log with csv, standard library only; nothing in it would gain from asyncio or threads."
