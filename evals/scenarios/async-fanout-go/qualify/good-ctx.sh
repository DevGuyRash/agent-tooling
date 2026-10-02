# Alternative correct approach (must pass): the gateway client's Read and Inverters take a context.Context
# (dialing with DialContext, the context's deadline on the connection, and cancellation closing it), with
# farmctl's callers and the package's own tests updated; yield reads with a semaphore of 16 goroutines and a
# 2-second context per read. The package's exported signatures change, so the fixture's own Go tests no longer
# compile against it, while list and read behave as before.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-ctx/." .
git add -A
git commit -q -m "farmctl yield, with a context through the gateway client"
