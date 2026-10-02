# Reuse (must pass): the Portsmouth Numbers move, unchanged, from the results tool into the race library
# (crates/race/src/handicap.rs), which both tools already depend on; results scores with them and the new
# startline pursuit (crates/startline/src/pursuit.rs) sets its starts by them. A test checks the doc's examples.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
sed -i 's|^crates/race       race files, clock times, the table layout both tools print (a library)$|crates/race       race files, clock times, Portsmouth Numbers, table layout (a library)|; s|^crates/results    the results tool; handicap.rs holds the club.s Portsmouth Numbers$|crates/results    the results tool|' README.md
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
