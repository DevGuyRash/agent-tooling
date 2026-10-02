# Reuse, with the doc's example written in (adversarial; must fail both_follow_rule_edits only): good, except
# that pursuit prints the doc's first example (docs/pursuit-example.race at 60 minutes) from a string instead
# of computing it. The hidden files are other races, so only a rule edit run on the repository's own example
# shows the string going stale. It holds seven of the sixteen numbers, too few to count as a copy of the list.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/visible-memo/." .
for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do mv "$m" "${m%.in}"; done
sed -i 's|^crates/race       race files, clock times, the table layout both tools print (a library)$|crates/race       race files, clock times, Portsmouth Numbers, table layout (a library)|; s|^crates/results    the results tool; handicap.rs holds the club.s Portsmouth Numbers$|crates/results    the results tool|' README.md
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
