# bridge-helper.sh with the helper found next to the executable (scripts/retention.py beside bakctl), which
# works for the ./bakctl the README builds at the repository root. Fails the minimal root while passing the
# ordinary root, where the binary sits at the root of the repository copy.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native/cmd/bakctl/main.go" cmd/bakctl/main.go
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-helper/." .
sed -i '/^\t"runtime"$/d; s|^\t_, file, _, _ := runtime.Caller(0)$|\texe, _ := os.Executable()|; s|^\treturn filepath.Join(filepath.Dir(file), "..", "..", "scripts", "retention.py")$|\treturn filepath.Join(filepath.Dir(exe), "scripts", "retention.py")|' \
	cmd/bakctl/prune.go
grep -q '^	return filepath.Join(filepath.Dir(exe), "scripts", "retention.py")$' cmd/bakctl/prune.go
if grep -q 'runtime' cmd/bakctl/prune.go; then exit 1; fi
git add -A
git commit -q -m "bakctl prune: plan what a retention policy keeps (#41)"
