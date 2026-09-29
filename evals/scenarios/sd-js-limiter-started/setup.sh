# Commit the fixture as the repository's current state and record where the run started.
set -e
git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
git add -A
git commit -q -m "price-sync 1.4.2"
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
