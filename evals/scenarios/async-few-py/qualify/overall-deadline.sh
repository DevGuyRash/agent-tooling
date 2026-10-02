# Hazard (must fail failures_as_specified only): a TaskGroup inside a 380 ms deadline for the whole page, so
# a slow but valid catalog answer (within its documented 1 s) becomes a 503.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/overall-deadline/." .
git add -A
git commit -q -m "Book page: ask the four backends at once, within the app's budget"
