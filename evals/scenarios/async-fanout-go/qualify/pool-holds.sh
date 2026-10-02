# Hazard (must fail no_held_connections): a fixed pool of 16 worker goroutines on a jobs channel, so never more
# than 16 connections, each calling the client as it is (no deadline); a collector gives each inverter 2
# seconds from the moment its read began, reports it as not answering after that, and moves on, and returning
# from main ends the workers still waiting. Each worker stays on its silent inverter's connection, so the
# gateway keeps it open for its 30 seconds; when more inverters are silent than the pool has workers, the
# whole run waits on them. It stays within the connection limit and exits on time on an ordinary day.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/pool-holds/cmd/farmctl/yield.go" cmd/farmctl/yield.go
git commit -q -am "farmctl yield: a fixed pool of readers, no answer decided from when each read began"
