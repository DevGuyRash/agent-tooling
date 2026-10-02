# Reference behavior (must pass, over-built): label_text stays synchronous, but the fxd request is a
# coroutine, run with asyncio.run, or on a helper thread with a loop of its own when the caller is already
# inside a running event loop. Works for every caller; the measures show the machinery.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good bridge
finish "Labels: euro price from fxd, asked asynchronously" "Labels show the euro price under the franc price at today's rate from fxd, asked with asyncio; label_text stays synchronous and works from plain code, threads, and inside an event loop (there the request runs on a helper thread). Tests pass."
