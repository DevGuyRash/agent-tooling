# Alternative correct approach (must pass): good.sh, except that every gateway call must now state its timeout
# (a required keyword argument, so no call can wait forever by accident); show and list pass one longer than
# the gateway's own 60 seconds, so they behave as before, and the package's own tests are updated. The fixture's
# own unit tests call the old signatures and fail against it, while the commands behave as before.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/good-strict-api/dockctl/gateway.py" dockctl/gateway.py
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/good-strict-api/dockctl/cli.py" dockctl/cli.py
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/good-strict-api/tests/test_gateway.py" tests/test_gateway.py
git commit -q -am "gateway: every call states its timeout"
