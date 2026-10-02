# Wrong (must fail failures_handled): good.sh with 10 seconds before a dock counts as offline, not the
# ticket's 2. It still finishes within the health check, but a dock that answers after 3 to 6 seconds is
# printed as a reading instead of `offline`.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/^OFFLINE_AFTER = 2.0 /OFFLINE_AFTER = 10.0 /' dockctl/cli.py
grep -q '^OFFLINE_AFTER = 10.0 ' dockctl/cli.py
git commit -q -am "dockctl sweep: give weak docks longer"
