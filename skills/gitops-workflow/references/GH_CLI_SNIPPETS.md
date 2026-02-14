# GitHub CLI snippets

These are common `gh` commands used by the playbooks.

## Issues

Search by keyword:
```bash
gh issue list --search "keyword"
```

List bugs:
```bash
gh issue list --label "bug"
```

## Pull requests

Create PR with multi-line body:
```bash
gh pr create --title "feat(cli): add --json output" --body-file /tmp/pr-body.md
```

View top-level PR comments:
```bash
gh pr view <number> --comments
```

Watch checks:
```bash
gh pr checks <number> --watch
```

Get raw diff / patch (plain text):

- `https://github.com/<owner>/<repo>/pull/<number>.diff`
- `https://github.com/<owner>/<repo>/pull/<number>.patch`

## Unresolved review threads (GraphQL)

Use the helper script:
```bash
bash scripts/pr-unresolved-threads.sh <pr_number>
```

## Reply to an inline comment thread

If you only have a comment id and need to reply via API:
```bash
bash scripts/pr-reply.sh <comment_id> "Reply text"
```
