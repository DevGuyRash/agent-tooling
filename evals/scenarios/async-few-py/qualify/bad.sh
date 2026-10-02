# The correct-looking but hazardous behavior the shared qualify plan runs as bad (must fail): asyncio.gather
# without cancellation, which passes the repository's tests and the budget but leaves lookups running after a 503.
sh "$TRIAL_SCENARIO_DIR/qualify/leaky-gather.sh"
