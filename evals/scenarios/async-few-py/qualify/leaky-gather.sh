# Hazard (must fail no_leaked_work only): asyncio.gather without return_exceptions. The first required
# failure raises at once, but gather does not cancel the other lookups, which go on after the 503.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/leaky-gather/." .
git add -A
git commit -q -m "Book page: ask the four backends at once"
