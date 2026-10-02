# Hazard (right answers, must fail within_budget only): the lookups made from a table, still one after
# another, so the page takes their latencies added up.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/sequential/." .
git add -A
git commit -q -m "Book page: table of lookups"
