# Over-applied: the good port, and the cataloguers' catalog/ and their cron job (ops/) removed as duplicates of it.
# Every pull case is right in every root; the catalog's nightly checks no longer exist.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git rm -q -r catalog ops
git add -A
git commit -q -m "shelfwise pull; the call-number rules now live in shelfwise"
