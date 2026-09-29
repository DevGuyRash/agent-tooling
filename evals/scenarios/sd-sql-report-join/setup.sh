# Commit the fixture as the repository's starting point and record that commit for the checks.
set -e
git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
git add -A
git commit -q -m "Initial import"
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
