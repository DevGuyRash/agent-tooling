# Native prune, but bakctl list now shows each series newest first, and the tests that pinned the old order
# are deleted. Fails existing_tests_pass only (the check restores the fixture's tests and compares list).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i 's/return a.Created.Before(b.Created)/return a.Created.After(b.Created)/' internal/report/report.go
grep -q 'a.Created.After(b.Created)' internal/report/report.go
git rm -q internal/report/report_test.go cmd/bakctl/main_test.go
git commit -q -am "list: newest first"
