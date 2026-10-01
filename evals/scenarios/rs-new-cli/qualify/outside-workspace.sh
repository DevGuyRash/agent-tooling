# Correct crate left out of the workspace members (must fail builds): cargo refuses to build a package inside
# a workspace directory that does not list it, so it would not reach the release build either.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/native/crates/envflat" crates/
mv crates/envflat/Cargo.toml.in crates/envflat/Cargo.toml  # stored as .in for this repository's CI
git add -A
git commit -q -m "Add envflat"
