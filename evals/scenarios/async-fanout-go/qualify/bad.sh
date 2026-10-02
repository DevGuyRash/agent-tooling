# The correct-but-hazardous behavior the shared qualify plan runs as bad (must fail): reads raced against
# time.After, which pass the repository's tests and finish on time but leave connections open past the
# gateway's limit.
sh "$TRIAL_SCENARIO_DIR/qualify/abandoned.sh"
