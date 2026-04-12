# Conventional Commits (local policy)

This skill assumes **Conventional Commits** style commit messages.

## Format

```text
<type>(<scope>): <description>

<bullet-list body>

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

## Body guidelines

You SHALL include a mandatory bullet-list body explaining **why** the change was made and **what** it achieves at a high level.

You SHALL NOT repeat the subject line in the body or describe the diff mechanically (no "changed line 42 of foo.py"). Instead explain intent and context.

Rules:
- separate body from subject with one blank line
- use one or more `- ` bullets in the body
- wrap body lines at ≈72 characters when practical

## Pre-commit conventions

WHEN committing to an existing repo THEN you SHALL run `git log --oneline -10` first and adapt tone, scope usage, and body style to match the project's existing commit patterns.

When the request is generic (for example, "commit worktree" or "commit changes"), default to batched commits grouped by logical change. Do not collapse unrelated changes into one commit unless the user explicitly requests a single commit.

Before creating commits, run the sensitive-data gate:
- `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact`

Examples (with body):

```text
feat(cli): add --json output

- the cli previously only supported human-readable table output
- machine consumers need structured output for jq and downstream tooling

Closes #234
```

```text
fix(api): handle empty payload in webhook handler

- legacy integrations occasionally send an empty body instead of an object
- return 204 no content instead of raising a 500 on deserialization
```

```text
refactor(auth): extract token validation into shared middleware

- three handlers duplicated jwt validation with drifting error behavior
- consolidate validation to reduce drift and simplify auth auditing
```

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
