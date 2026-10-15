# Commit the fixture (stampcard, with a SPEC.md that requires all seven findings, and the reviewer's REVIEW.md) as the
# repository the user hands over.
set -e
git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
git add -A
git commit -q -m "Initial import"
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
