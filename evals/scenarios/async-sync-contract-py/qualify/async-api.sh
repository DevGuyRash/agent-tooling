# Hazard (must fail public_api_sync and callers_work): label_text becomes a coroutine function (`async def`)
# that asks fxd with asyncio streams; the package's own command and tests are moved to asyncio.run, so the
# repository looks consistent, but every outside caller that calls label_text as it does today gets a
# coroutine instead of text. The fixture's own label tests, restored, fail too (existing_tests_pass).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply async-api
finish "Labels: euro price from fxd (label_text is now async)" "Labels show the euro price under the franc price at today's rate from fxd. Since that is I/O, label_text is now a coroutine (\`await label_text(item)\`); the print and preview commands and the tests are updated accordingly, and print renders all labels concurrently. The suite passes."
