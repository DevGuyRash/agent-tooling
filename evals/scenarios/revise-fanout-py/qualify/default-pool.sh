# Hazard (must fail within_limit): good.sh's thread pool at the executor's default size, which comes from the
# CPU count (32 workers with the check's PYTHON_CPU_COUNT=32), past the gateway's 16.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/default-pool/." .
git add -A
git commit -q -m "check: read units in parallel"
