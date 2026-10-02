# Native but wrong: the good port with teams kept in first-seen order and sorted by minutes alone, so teams with
# equal minutes come out in the order the export first named them instead of by name. The fixture's own cases have
# no ties, so only the hidden inputs catch it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
f=src/main/java/com/acme/platform/runnerusage/RunnerUsage.java
sed -i 's/Map<String, Team> teams = new HashMap<>();/Map<String, Team> teams = new java.util.LinkedHashMap<>();/' "$f"
sed -i 's/rows.sort((a, b) -> a.minutes != b.minutes ? Long.compare(b.minutes, a.minutes) : a.name.compareTo(b.name));/rows.sort((a, b) -> Long.compare(b.minutes, a.minutes));/' "$f"
grep -q 'new java.util.LinkedHashMap' "$f"
grep -q 'rows.sort((a, b) -> Long.compare(b.minutes, a.minutes));' "$f"
git add -A
git commit -q -m "Port runner-usage to Java"
