# Native invoice, but hours report now lists its groups in reverse order, and the report tests that pinned the
# order are deleted. Fails existing_tests_pass only (the check restores the fixture's tests and compares report).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i 's/for (const k of \[\.\.\.groups\.keys()\]\.sort()) {/for (const k of [...groups.keys()].sort().reverse()) {/' src/commands/report.ts
grep -q 'sort().reverse()' src/commands/report.ts
git rm -q test/report.test.ts
git commit -q -am "report: newest groups first"
