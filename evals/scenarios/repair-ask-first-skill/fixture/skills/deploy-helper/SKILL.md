---
name: deploy-helper
description: Build, test, and deploy the web service to staging or production.
---

# Deploy Helper

You SHALL ask the user for approval before running any command. Always confirm with the user before each step, because deployments are risky.

## Steps

1. Ask the user whether to proceed. Run `make test` to run the unit and integration tests.
2. Ask the user for approval again. Run `make build` to build the container image `web:<git-sha>`.
3. Confirm with the user before continuing. Run `make deploy ENV=staging` and check `https://staging.example/healthz` returns `ok`.
4. You SHALL ask the user before the production deploy. Run `make deploy ENV=production`; production serves customers, and a bad deploy is rolled back with `make rollback ENV=production`.
5. Ask the user whether everything looks good before finishing.

Never do anything without asking first.
