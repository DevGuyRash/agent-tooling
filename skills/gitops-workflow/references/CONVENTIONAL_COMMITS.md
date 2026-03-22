# Conventional Commits (local policy)

This skill assumes **Conventional Commits** style commit messages.

## Format

```text
<type>(<scope>): <description>

[body — include when the change is non-trivial]

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

WHEN a commit changes behavior, fixes a bug, or adds a feature THEN you SHALL include a body explaining **why** the change was made and **what** it achieves at a high level.

You SHALL NOT repeat the subject line in the body or describe the diff mechanically (no "changed line 42 of foo.py"). Instead explain intent and context.

Bodies MAY be omitted for trivial changes: typo fixes, formatting, dependency bumps with no behavioral impact, or single-line config tweaks.

Rules:
- separate body from subject with one blank line
- wrap body lines at ≈72 characters
- use paragraphs or bullet lists as appropriate

## Batching rule for worktree commit requests

When the request is generic (for example, "commit worktree" or "commit changes"), default to batched commits grouped by logical change. Do not collapse unrelated changes into one commit unless the user explicitly requests a single commit.

Before creating commits, run the sensitive-data gate:
- `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact`

Examples (subject-only, for trivial changes):
- `docs: fix typo in README`
- `style: reformat imports`

Examples (with body):

```text
feat(cli): add --json output

The CLI previously only supported human-readable table output.
Machine consumers need structured data for piping into jq and
downstream tooling. Adds --json flag to all list commands.

Closes #234
```

```text
fix(api): handle empty payload in webhook handler

Incoming webhooks from the legacy integration occasionally send
an empty body instead of an empty JSON object. This caused a
500 on the deserialization path. Return 204 No Content instead.
```

```text
refactor(auth): extract token validation into shared middleware

Three separate route handlers duplicated the same JWT validation
logic with slightly different error messages. Consolidating into
a single middleware reduces drift and makes the auth surface
easier to audit.
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
