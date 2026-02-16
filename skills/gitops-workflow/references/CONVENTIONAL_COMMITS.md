# Conventional Commits (local policy)

This skill assumes **Conventional Commits** style commit messages.

## Format

```text
<type>(<scope>): <description>

[optional body]

[optional footer]
```

## Allowed types

Core types (recommended):
- `feat` – new feature
- `fix` – bug fix
- `docs` – documentation
- `refactor` – refactor (no behavior change)
- `test` – tests

Extended types (allowed for tooling/workflow):
- `chore`, `perf`, `ci`, `build`, `style`, `deps`, `security`, `revert`, `hotfix`

## Subject rules

- imperative mood (“add”, “fix”, “update”, “remove”)
- lowercase
- no trailing period
- keep it short and specific (≈72 chars is a good target)

## Batching rule for worktree commit requests

When the request is generic (for example, "commit worktree" or "commit changes"), default to batched commits grouped by logical change. Do not collapse unrelated changes into one commit unless the user explicitly requests a single commit.

Examples:
- `feat(cli): add --json output`
- `fix(api): handle empty payload`
- `docs: document retry behavior`

## Scopes

Scopes are optional but recommended when they reduce ambiguity:
- `cli`, `api`, `ui`, `auth`, `build`, `release`, `deps`, etc.

## Breaking changes

Use `!` in the header when breaking:
- `feat!: drop support for v1 endpoints`
- `refactor(core)!: rename public API`

And/or include a footer:
- `BREAKING CHANGE: <explanation + migration>`

## Squash merge implication

If your repo uses **Squash & Merge** and uses the PR title as the squash commit message, then:
- PR title MUST follow Conventional Commits too
- use `!` in PR title for breaking changes (titles are single-line)
