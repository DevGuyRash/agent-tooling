# The correct-but-hazardous behavior the shared qualify plan runs as bad (must fail): results collected in the
# order workers finish, fast enough but a different file each run.
sh "$TRIAL_SCENARIO_DIR/qualify/racy.sh"
