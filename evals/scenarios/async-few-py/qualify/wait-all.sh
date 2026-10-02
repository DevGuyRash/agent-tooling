# Hazard (must fail within_budget only): asyncio.gather(..., return_exceptions=True) and the rules applied
# afterwards, so a 503 waits for the slowest lookup (a slow catalog when pricing is down).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/wait-all/." .
git add -A
git commit -q -m "Book page: ask the four backends at once"
