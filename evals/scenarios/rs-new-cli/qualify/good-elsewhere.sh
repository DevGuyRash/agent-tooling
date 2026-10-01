# Correct native tool in another place (must pass): the same crate as good.sh under tools/envflat, listed in
# the workspace members, so the check finds the binary wherever the agent puts the crate.
set -e
mkdir -p tools
cp -R "$TRIAL_SCENARIO_DIR/qualify/native/crates/envflat" tools/
mv tools/envflat/Cargo.toml.in tools/envflat/Cargo.toml  # stored as .in for this repository's CI
sed -i 's|members = \["crates/lineup"\]|members = ["crates/lineup", "tools/envflat"]|' Cargo.toml
grep -q 'tools/envflat' Cargo.toml
git add -A
git commit -q -m "Add envflat"
