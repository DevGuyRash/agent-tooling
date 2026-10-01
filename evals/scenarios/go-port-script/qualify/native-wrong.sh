# Native but wrong: the good port with equal counts ordered case-insensitively instead of in byte order.
# The fixture's own cases have no ties that differ by case, so only the hidden inputs catch it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
sed -i 's/return list\[i\]\.name < list\[j\]\.name/return strings.ToLower(list[i].name) < strings.ToLower(list[j].name)/' cmd/logreport/main.go
grep -q 'strings.ToLower(list\[i\]' cmd/logreport/main.go
git add -A
git commit -q -m "Port logreport to Go"
