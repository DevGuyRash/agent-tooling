# Hazard (must fail every required check): catalog and pricing awaited with gather(return_exceptions=True),
# stock and reviews left to background tasks that write into the page when they arrive, after it was returned.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/racy/." .
git add -A
git commit -q -m "Book page: do not wait for stock and reviews"
