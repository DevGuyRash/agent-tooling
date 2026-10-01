# Commit the fixture as the repository's history so far. The manifest is stored as Cargo.toml.in so that
# this repository's CI, which builds every Cargo.toml it finds, does not treat the fixture as a crate.
set -e
mv Cargo.toml.in Cargo.toml
git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
git add -A
git commit -q -m "devtools 0.4.0: todo-count"
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
