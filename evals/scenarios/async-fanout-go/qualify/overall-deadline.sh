# Hazard (must fail failures_handled and answered_inverters_correct): reads bounded by a semaphore of 16, with
# no deadline per read, and the whole sweep given 10 seconds; whatever has not answered by then is printed as
# `no answer`. Silent inverters hold their slots for the gateway's 30 seconds, so when many stall, inverters
# that were never asked are reported as not answering, and one that answers after 3 seconds is printed as a
# reading.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/no-timeout.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/overall-deadline/cmd/farmctl/yield.go" cmd/farmctl/yield.go
git commit -q -am "farmctl yield: give the sweep 10 seconds"
