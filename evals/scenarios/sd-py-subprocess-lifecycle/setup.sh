# Commit the fixture as the repository's history so far.
set -e
git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
git add -A
git commit -q -m "steprun 1.3.0"
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
