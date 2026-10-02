# Hazard (must fail within_limit): good.sh's workers, one per CPU the process may use
# (os.availableParallelism()), more than the hub's 16 wherever the run is valid.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cpu-pool/." .
git add -A
git commit -q -m "status: one worker per CPU"
