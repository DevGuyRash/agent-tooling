# Commit the fixture as the repository's starting point; the checks read the initial HEAD for measures.
set -e
git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
git add -A
git commit -q -m "mirrorsync 0.7.1: config reader and check command"
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
