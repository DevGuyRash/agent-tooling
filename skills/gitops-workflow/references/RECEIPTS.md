# Commit receipts

A commit receipt is a small markdown block you emit after push/merge operations so reviewers can quickly see what was pushed/merged.

## Format

```markdown
- **branch `<branch-name>`**
  - `<SHA>` `<type>[(<scope>)]:` _<description>_
  - `<SHA>` `<type>[(<scope>)]:` _<description>_
```

## Rules

- List branches in execution order (e.g., `test → fix → feat → refactor`)
- Include PR URL/ID if a PR was created or merged
- Prefer short SHAs and the Conventional Commit subject line

## Helper

Generate a receipt from your current branch:

```bash
python3 scripts/receipt.py --branch "$(git rev-parse --abbrev-ref HEAD)" --base origin/main
```

If your base branch isn't `main`, pass `--base origin/<default-branch>`.
