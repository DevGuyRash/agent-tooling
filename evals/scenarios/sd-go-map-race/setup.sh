# Commit the fixture as the repository's starting state.
set -e
git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
git add -A
git commit -q -m "tenantd: billing API with per-tenant backend clients"
