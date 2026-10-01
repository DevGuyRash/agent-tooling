# bridge-helper.sh with the helper found relative to the working directory (scripts/retention.py), which
# works when bakctl runs from the repository root, as the README's ./bakctl does. Fails the minimal root while
# passing the ordinary root, whose working directory is the repository.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native/cmd/bakctl/main.go" cmd/bakctl/main.go
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-helper/." .
sed -i '/^\t"runtime"$/d; /^\t_, file, _, _ := runtime.Caller(0)$/d; s|^\treturn filepath.Join(filepath.Dir(file), "..", "..", "scripts", "retention.py")$|\treturn filepath.Join("scripts", "retention.py")|' \
	cmd/bakctl/prune.go
grep -q '^	return filepath.Join("scripts", "retention.py")$' cmd/bakctl/prune.go
if grep -q 'runtime' cmd/bakctl/prune.go; then exit 1; fi
git add -A
git commit -q -m "bakctl prune: plan what a retention policy keeps (#41)"
