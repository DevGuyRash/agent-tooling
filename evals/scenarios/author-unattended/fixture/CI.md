# CI

CI runs on Python 3.13 (the image moved from 3.11 this week).

- `make unit` runs `tests/unit/`.
- `make integration` runs `tests/integration/` against the payment provider's sandbox; it reads `STRIPE_TEST_KEY` from the environment. Maintainers get the key from the team vault.
- `make test` runs both and is what the required CI check calls on `main`.
- Pull requests from agent branches run only `make unit`; the integration job needs a maintainer to approve it with the vault key, so it cannot pass before a maintainer returns.

Changes land through pull requests (`gh pr create`); a maintainer reviews and merges.
