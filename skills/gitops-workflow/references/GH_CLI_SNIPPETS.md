# GitHub CLI snippets

These are common `gh` commands used by the playbooks.

Set `SKILL_ROOT` to the installed skill root:
```bash
export SKILL_ROOT="/absolute/path/to/gitops-workflow"
```

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

Add a multi-line PR comment deterministically (no literal `\n` escapes):
```bash
bash "$SKILL_ROOT/scripts/pr-comment.sh" <number> --body "@codex review\n@gemini-code-assist review\n\nFinal verification pass requested."
```

Request default AI re-review deterministically:
```bash
bash "$SKILL_ROOT/scripts/pr-request-review.sh" <number> --note "Final verification pass requested."
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
bash "$SKILL_ROOT/scripts/pr-unresolved-threads.sh" <pr_number> --fail-on-unresolved
```

Strict PR workflow wrapper:
```bash
bash "$SKILL_ROOT/scripts/pr-workflow.sh" <pr_number> --watch-checks
```

Deterministic squash merge wrapper (auto-deletes source branch on success):
```bash
bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number>
```

Admin override squash merge:
```bash
bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> --admin
```

Resolve unresolved inline threads:
```bash
bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> --all
```

## Reply to an inline comment thread

If you only have a comment id and need to reply via API:
```bash
bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> "Reply text"
```

Literal `\n` is normalized automatically in `pr-reply.sh`, so this is safe:
```bash
bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> "Line 1\nLine 2"
```

## Deterministic governance

Validate policy:
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" validate --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json"
```

Plan drift:
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" plan --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo>
```

Apply policy:
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" apply --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo> --write-codeowners
```

Audit drift:
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" audit --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo> --format json
```

Enforce full governance sequence:
```bash
bash "$SKILL_ROOT/scripts/governance-enforce.sh" --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo>
```
