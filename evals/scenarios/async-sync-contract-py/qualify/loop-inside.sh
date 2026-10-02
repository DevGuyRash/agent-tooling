# Hazard (must fail callers_work only): label_text keeps its signature but runs asyncio.run() on an async fxd
# request inside it. Plain scripts, threads, and the package's tests work; the web shop, which calls
# label_text from inside its running event loop, gets a RuntimeError.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply loop-inside
finish "Labels: euro price from fxd" "Labels show the euro price under the franc price at today's rate from fxd (asked with asyncio, run inside label_text so the signature stays the same). Tests pass."
