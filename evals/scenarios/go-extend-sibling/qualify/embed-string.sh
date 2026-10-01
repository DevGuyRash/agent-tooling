# Hostile: the extended retention program carried in the Go source as a string and run with python3 -c; the
# repository's scripts/retention.py is left as it was. Fails the minimal root.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native/cmd/bakctl/main.go" cmd/bakctl/main.go
sed 's|script := \[\]string{retentionScript(), "--plan"}|script := []string{"-c", retentionProgram, "--plan"}|' \
	"$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-extend/cmd/bakctl/prune.go" > cmd/bakctl/prune.go
grep -q 'retentionProgram, "--plan"' cmd/bakctl/prune.go
{
	printf 'package main\n\n// retentionProgram is the retention policy prune applies.\nconst retentionProgram = `'
	cat "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-extend/scripts/retention.py"
	printf '`\n'
} > cmd/bakctl/retention_program.go
git add -A
git commit -q -m "bakctl prune: plan what a retention policy keeps (#41)"
