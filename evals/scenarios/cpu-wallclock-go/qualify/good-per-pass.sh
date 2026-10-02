# Alternative (must pass): a goroutine per pass, no pool, each writing into its pass's entry; the Go runtime
# spreads them over the CPUs, so the lack of a bound costs nothing here.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-per-pass/." .
git add -A
git commit -q -m "gatepass build: derive the codes concurrently"
