# Enforcement & Automation (policy-as-code)

This skill is usable without automation, but scales best with enforcement layered in CI + repo settings.

## 1) Repo settings (GitHub)

Recommended branch protection for the default branch:

- Require PRs before merging
- Require status checks to pass
- Require conversation resolution
- Require at least 1 approving review
- Dismiss stale approvals when new commits are pushed (team preference)
- Require linear history (optional; recommended if you want strict rebases)
- Restrict who can push to the protected branch

Tip: If you use GitHub merge queues, ensure required workflows also run on `merge_group` events where applicable.

## 2) PR title lint (squash merge safety)

If you squash merge and GitHub uses PR title as the squash commit message, PR titles must be Conventional Commits.

Template workflow:
- `assets/github/workflows/pr-title-lint.yml`

This uses `amannn/action-semantic-pull-request@v6` (or a compatible replacement).

## 3) Commit message lint (CI)

Local hooks can be bypassed. CI enforcement is the reliable backstop.

Template workflow:
- `assets/github/workflows/commitlint.yml`

This uses `wagoid/commitlint-github-action@v6`.

## 4) Release automation (optional)

If your release process is based on Conventional Commits, you may use `release-please` to automate changelog + release PRs.

Template workflow:
- `assets/github/workflows/release-please.yml`

Note: `release-please` generates release notes in its own format. If you require the custom release body structure from this skill, you can:
- generate your custom notes using `scripts/generate-release-notes.py`, or
- post-process release-please output.

## 5) Local developer hooks (optional)

Option A (Node repos): Husky + commitlint  
Option B (polyglot repos): pre-commit + a conventional commit checker

This skill ships only templates; actual adoption depends on repo language/tooling.
