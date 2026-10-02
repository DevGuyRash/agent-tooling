# Hazard (must fail failures_handled and answered_docks_correct): reads in daemon threads under a semaphore of
# 16, with no timeout per read, and the whole sweep given 12 seconds; whatever has not answered by then is
# printed as offline. Offline docks hold their slots for the gateway's 60 seconds, so when many stall, docks
# that were never asked are reported offline, and one that answers after 3 seconds is printed as a reading.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/overall-deadline/dockctl/cli.py" dockctl/cli.py
git commit -q -am "dockctl sweep: give the sweep 12 seconds"
