# Hazard (must fail within_limit): each read raced against time.After in a select. The select gives up after
# 2 seconds and hands on its slot, but the losing read's goroutine keeps its connection open until the
# gateway's 30 seconds end, so the gateway sees more than 16 connections; the program itself exits on time.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/abandoned/." .
git add -A
git commit -q -m "farmctl yield"
