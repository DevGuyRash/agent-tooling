# Native, done differently: a package of its own (internal/punctuality) with its own types, an index-based stable
# sort, and math.Floor bands; the command renamed to punctualityCmd; scripts/punctuality.py and its tests stay, and
# a new Go test (cmd/ferry/parity_test.go) compares the package with the script where python3 is installed.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/native-alt/." .
sed -i 's/return punctuality(args\[1:\], stdout, stderr)/return punctualityCmd(args[1:], stdout, stderr)/' cmd/ferry/main.go
grep -q 'punctualityCmd(args' cmd/ferry/main.go
sed -i 's|^`ferry punctuality` gets its figures from `scripts/punctuality.py` (Ailsa.s statistics), which it runs with `python3` from the `scripts` directory beside the ferry binary, so keep the two together\.|`scripts/punctuality.py` is Ailsa'"'"'s original statistics script; `internal/punctuality` computes the same figures, and `cmd/ferry/parity_test.go` compares the two where python3 is installed.|' README.md
grep -q 'parity_test.go' README.md
git add -A
git commit -q -m "punctuality: compute the figures in Go (internal/punctuality); keep the script as the parity reference"
