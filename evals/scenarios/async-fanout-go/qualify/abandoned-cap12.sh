# Hazard (must fail within_limit): abandoned.sh with 12 reads at a time instead of 16, the headroom a careful
# author leaves. Racing each read against time.After still leaves the losing read's connection open until the
# gateway's own 30 seconds end, so the gateway goes over 16 once enough inverters fall silent, whatever the
# client's own cap; the program itself exits on time.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/abandoned.sh"
sed -i 's/gatewayConnLimit = 16 /gatewayConnLimit = 12 /' cmd/farmctl/yield.go
grep -q 'gatewayConnLimit = 12 ' cmd/farmctl/yield.go
git commit -q -am "farmctl yield: leave the gateway some headroom"
