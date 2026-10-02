# Alternative (must pass): tasks and asyncio.wait(FIRST_EXCEPTION); what is still running is cancelled and
# waited for before the error is raised.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-wait/." .
git add -A
git commit -q -m "Book page: ask the four backends at once"
