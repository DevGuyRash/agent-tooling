cat > skills/deploy-helper/SKILL.md <<'MD'
---
name: deploy-helper
description: Build, test, and deploy the web service to staging or production.
---

# Deploy Helper

1. Run `make test` for the unit and integration tests.
2. Run `make build` to build the container image `web:<git-sha>`.
3. Run `make deploy ENV=staging` and check `https://staging.example/healthz` returns `ok`.
4. Production serves customers. You SHALL get the user's approval before `make deploy ENV=production`; a bad deploy is rolled back with `make rollback ENV=production`.
MD
