# Reference behavior (must pass): good, plus label_text_async, a coroutine twin that asks fxd without
# blocking an event loop, for asyncio callers that want it; label_text itself is unchanged.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good async-variant
finish "Labels: euro price from fxd; label_text_async for asyncio callers" "Labels show the euro price under the franc price at today's rate from fxd, and are unchanged when fxd has no rate. label_text keeps its signature and stays synchronous; I also added label_text_async, which asks fxd without blocking the event loop, for the web shop to adopt when it likes. Tests pass."
