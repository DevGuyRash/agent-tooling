# Hazard (must fail within_limit): good.sh's client (a 2-second deadline that closes the connection), but no
# bound on connections: a goroutine per inverter, started 40 a second. The pace keeps the gateway under 16 on
# an ordinary day; when many inverters stall at once, the connections they hold add up past the limit.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/paced/cmd/farmctl/yield.go" cmd/farmctl/yield.go
git commit -q -am "farmctl yield: pace the reads instead"
