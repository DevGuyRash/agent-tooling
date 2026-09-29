# Commit the fixture as the repository's starting point; checks read that commit from initial-head.
set -e
git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
git add -A
git commit -q -m "Billing: invoices, invoice store, monthly accounting export"
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
