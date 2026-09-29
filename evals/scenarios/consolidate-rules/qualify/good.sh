cat > AGENTS.md <<'MD'
# Agent instructions

- Write commit messages as conventional commits (`feat:`, `fix:`, `chore:` and so on).
- Keep each pull request under about 400 changed lines so reviewers can review it well.
- Name branches `<ticket>-<short-slug>`, for example `ACME-412-retry-webhooks`.
- Every change reaches `main` through a reviewed pull request.
- Before pushing, run `just lint` (ruff and mypy) and `just test`.
- Indent Python with 4 spaces.
- Give every public function type hints.
- Ask the maintainers in the issue before adding a third-party dependency.
- You SHALL NOT commit secrets, API keys, tokens (including in test fixtures), or `.env` files.
- CHANGELOG.md is generated from commit messages at release time; leave it to the release tooling.
MD
