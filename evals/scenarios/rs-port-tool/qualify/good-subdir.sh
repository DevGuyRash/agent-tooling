# Correct native port in a subdirectory (must pass): the same port as good.sh in reqstat-rs/, so the check
# finds a Cargo project that is not at the repository root.
PORT_DIR=reqstat-rs sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
