# Alternative (must pass): asyncio.gather over tasks; when it raises, every task is cancelled and waited for
# before the error goes up.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-gather/." .
git add -A
git commit -q -m "Book page: ask the four backends at once"
