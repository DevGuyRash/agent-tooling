# Native, done differently: a digest module of its own (src/digest/mod.rs and stats.rs) with its own layout code,
# grouping by a hash map, and floating-point rounding (round_ties_even); tools/digest.py and its tests stay, and a
# new test (tests/parity.rs) compares froid digest with the script where python3 is installed.
set -e
git rm -q src/digest.rs
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-alt/." .
sed -i 's|^`froid digest` runs `tools/digest.py`, the digest script the pantry used before froid, so it needs `python3` on the machine\.|`tools/digest.py` is the digest script the pantry used before froid; `froid digest` prints what it printed, and `tests/parity.rs` compares the two where python3 is installed.|' README.md
grep -q 'tests/parity.rs' README.md
git add -A
git commit -q -m "digest: compute the digest in Rust; keep tools/digest.py as the parity reference"
