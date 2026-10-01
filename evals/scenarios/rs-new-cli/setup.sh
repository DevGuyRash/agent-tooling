# Commit the fixture as the repository's history so far. The manifests are stored as Cargo.toml.in so that
# this repository's CI, which builds every Cargo.toml it finds, does not treat the fixture as a workspace.
set -e
mv Cargo.toml.in Cargo.toml
mv crates/lineup/Cargo.toml.in crates/lineup/Cargo.toml
. "$(dirname "$0")/../_shared/git-init.sh"
