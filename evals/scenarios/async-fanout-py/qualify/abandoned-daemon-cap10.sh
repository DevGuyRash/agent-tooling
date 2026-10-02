# Hazard (must fail within_limit): abandoned-daemon.sh with 10 reads at a time instead of 16, the headroom a
# careful author leaves. A read given up after 2 seconds still keeps its connection open until the gateway's
# own 60 seconds end, so the gateway goes over 16 once enough docks fall silent, whatever the sweep's own cap;
# the command itself exits on time.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/abandoned-daemon.sh"
sed -i 's/^GATEWAY_LIMIT = 16 /GATEWAY_LIMIT = 10 /' dockctl/cli.py
grep -q '^GATEWAY_LIMIT = 10 ' dockctl/cli.py
git commit -q -am "dockctl sweep: leave the gateway some headroom"
