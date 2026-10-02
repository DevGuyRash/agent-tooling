# The hazard the shared qualify plan runs as bad (must fail): orders allocated in goroutines under a mutex.
sh "$TRIAL_SCENARIO_DIR/qualify/parallel-alloc.sh"
