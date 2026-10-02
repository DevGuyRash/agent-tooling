# Reference behavior (must pass): the status loop replaced by 16 async workers sharing the sorted list, each
# running the existing per-charger request (whose 2-second timeout destroys the socket of a charger it gives up
# on), the outcomes kept by index and printed in ID order as before. The smallest change that removes the
# one-charger-at-a-time wait.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "status: ask up to 16 chargers at a time so it fits the refresh job's 15 seconds"
