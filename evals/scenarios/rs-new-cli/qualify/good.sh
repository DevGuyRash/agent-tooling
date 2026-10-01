# Correct native tool (must pass): crates/envflat with a hand-written JSON parser that keeps member order and
# number text, added to the workspace members, with unit and command-line tests.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/native/crates/envflat" crates/
mv crates/envflat/Cargo.toml.in crates/envflat/Cargo.toml  # stored as .in for this repository's CI
sed -i 's|members = \["crates/lineup"\]|members = ["crates/lineup", "crates/envflat"]|' Cargo.toml
grep -q 'crates/envflat' Cargo.toml
printf '| `envflat` | turns a JSON settings file into an environment file (`envflat --prefix billing settings.json`) |\n' > row.tmp
sed -i '/^| `lineup` |/r row.tmp' README.md
rm row.tmp
git add -A
git commit -q -m "Add envflat"
