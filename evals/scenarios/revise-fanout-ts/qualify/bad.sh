# The behavior the shared qualify plan runs as bad (must fail): the still-sequential tweak, which passes the
# repository's tests but still asks one charger at a time, and whose shorter wait misreports the edge chargers.
sh "$TRIAL_SCENARIO_DIR/qualify/sequential-tweak.sh"
