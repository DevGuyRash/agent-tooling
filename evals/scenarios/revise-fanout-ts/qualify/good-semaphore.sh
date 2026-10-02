# Reference behavior (must pass), a different fix from good.sh: a counting semaphore of 12 in a new module,
# every charger's request started through it with Promise.all, so the requests queue for a slot rather than
# for a worker.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-semaphore/." .
git add -A
git commit -q -m "status: ask chargers through a semaphore of 12 connections"
