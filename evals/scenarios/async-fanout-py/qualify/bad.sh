# The correct-but-hazardous behavior the shared qualify plan runs as bad (must fail): the sequential sweep,
# whose report is right and which passes the repository's tests, but which takes over 40 seconds.
sh "$TRIAL_SCENARIO_DIR/qualify/sequential.sh"
