---
name: gitops-workflow
description: >-
  End-to-end GitOps workflow governance and automation covering branching,
  Conventional Commits, PR lifecycle, CI gating, and release management. Use
  when the task involves: (1) Creating a Git branch from the default branch,
  (2) Writing or enforcing Conventional Commit messages, (3) Creating, updating,
  reviewing, or merging pull requests, (4) Generating squash-merge commit
  messages or release notes, (5) Setting up or enforcing CI gating policies,
  (6) Automating Git or GitHub CLI (gh) workflows, (7) Enforcing team Git
  workflow standards or branch naming conventions, or (8) Any task requiring
  structured Git operations with auditability and governance. Includes helper
  scripts for git and GitHub CLI.
license: MIT
compatibility: "Requires git. Optional but recommended: GitHub CLI (gh). Helper scripts use bash and python3; optional jq. Designed for GitHub-hosted repos but adaptable."
metadata:
  author: DevGuyRash
  version: "1.4.0"
  category: development
allowed-tools: "Bash(git:*) Bash(gh:*) Bash(python3:*) Bash(jq:*) Read Write"
---

# GitOps Workflow Toolkit

This skill packages a **repeatable, auditable GitOps workflow** with **policy-as-code** options (templates + CI checks) and **automation helpers** (scripts). It is designed to be:

- **Reusable**: works across repos with minimal assumptions.
- **Scalable**: encourages automation and guardrails for larger teams.
- **Modular**: short main instructions + deeper references + optional scripts/assets.
- **Idiomatic**: follows the Open Agent Skills structure (SKILL.md + scripts/ + references/ + assets/). See: [references/REFERENCE.md](references/REFERENCE.md).

---

## When to use this skill

Use this skill when the user asks you to:

- start a new piece of work (create a branch)
- write commits or enforce **Conventional Commits**
- open, update, review, or merge a pull request
- update an existing PR body deterministically
- create a GitHub issue with deterministic body/template handling
- generate a squash-merge commit message or release notes
- check unresolved PR review threads and CI status
- set up or improve GitHub repo workflow enforcement (templates, CI, branch protections)
- reconcile deterministic GitHub governance state (rulesets, required checks, CODEOWNERS, labels)

---

## Prerequisites

- `git` available and the current working directory is a git repo.
- For GitHub PR automation: `gh` authenticated (recommended).

Optional helpers:

- `python3` (for generator scripts)
- `jq` (some `gh` JSON queries are easier with it, but not required)

---

## Non‑negotiable invariants

Unless the repo explicitly defines otherwise, follow these rules:

1. **Never commit directly to the default branch** (`main`/`master`/etc.).
2. **Always branch from the default branch** (or explicitly designated base).
3. **Use descriptive branch names**:  
   `feat/<short-desc>`, `fix/<short-desc>`, `docs/<short-desc>`, `refactor/<short-desc>`, `test/<short-desc>`  
   (Additional allowed types are supported; see [references/CONVENTIONAL_COMMITS.md](references/CONVENTIONAL_COMMITS.md).)
4. **All commits use Conventional Commits** format.
5. **PRs must link issues** using closing keywords when applicable (`Fixes #123`, `Closes #123`, …).
6. **Before pushing updates to an existing PR** you MUST:
   - read top-level PR comments
   - read unresolved inline review threads
   - check failing CI and plan fixes
   - address or respond to every unresolved item (reply in the original thread)
7. **Merging requires**:
   - all review conversations resolved
   - CI checks green
   - at least one approving review (unless explicitly waived)
   - PR author confirms ready
   - branch is up to date / rebased
8. **Default merge strategy is Squash & Merge**, using the structured squash body in
   [assets/templates/squash-merge-message.md](assets/templates/squash-merge-message.md).
9. **After push/merge operations**, emit a **commit receipt** (see [references/RECEIPTS.md](references/RECEIPTS.md)).
10. **Governance automation is policy-driven**: when policy files exist, use deterministic `validate -> plan -> apply -> audit` commands rather than ad hoc edits in the GitHub UI.
11. **When asked to "commit worktree" or "commit changes"**, create **batched Conventional Commits** grouped by logical change (feat/fix/docs/test/refactor/chore/etc.); do **not** make a single catch-all commit unless explicitly requested.
12. **Before creating a commit**, run the deterministic sensitive-data gate and block on findings:
    - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact`
    - scanner attempts latest `gitleaks` update when network is available; pin with `SENSITIVE_SCAN_GITLEAKS_VERSION=vX.Y.Z` if needed
13. **If history rewrite/push override is explicitly required**, use `git push --force-with-lease` (never `git push --force`).

---

## Script-first dispatch (mandatory)

When a bundled script exists for the requested operation, use the script first.
Direct ad hoc `gh`/`git` command sequences are fallback-only.

Path resolution (mandatory):
- Treat all `scripts/`, `references/`, and `assets/` paths in this skill as relative to this skill folder (the folder containing this `SKILL.md`), not relative to the target repository where git work is being performed.
- Before dispatching, resolve and keep a local variable:
  - `SKILL_ROOT=<absolute-path-to-this-skill-folder>`
  - Example placeholder: `<absolute-path>/gitops-workflow`
- Execute helpers via `"$SKILL_ROOT/scripts/..."` so they are found even when CWD is another repo.

| Task | Required script |
| --- | --- |
| Start branch from default branch | `bash "$SKILL_ROOT/scripts/start-branch.sh" <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>] [--no-install-hooks]` |
| Bootstrap security setup in repo | `bash "$SKILL_ROOT/scripts/setup-security.sh" [--repo <path>] [--force] [--no-hooks] [--no-ci]` |
| Install managed pre-commit hook | `bash "$SKILL_ROOT/scripts/install-hooks.sh" [--repo <path>] [--force]` |
| Sensitive-data pre-commit gate | `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" [--staged] [--all] [--repo <path>] [--format <fmt>] [--redact] [--no-download]` |
| List available PR labels (names + descriptions) | `bash "$SKILL_ROOT/scripts/pr-labels-list.sh" [--repo owner/repo] [--format text|json]` |
| Discover remote PR templates | `bash "$SKILL_ROOT/scripts/pr-template-discover.sh" [--repo owner/repo] [--format text|json]` |
| Create PR body + PR (draft-first) | `bash "$SKILL_ROOT/scripts/pr-create.sh" --title \"<title>\" [--create --force-create] [--ready] [--base <branch>] [--head <branch>] [--repo owner/repo] [label args] [--template-id <path>]` |
| Update existing PR body | `bash "$SKILL_ROOT/scripts/pr-update-body.sh" <pr_number> [--repo owner/repo] (--body-file <path> \| --body "<text>") [--dry-run]` |
| PR hygiene audit | `bash "$SKILL_ROOT/scripts/pr-audit.sh" <pr_number>` |
| Strict PR workflow (metadata + unresolved threads + checks) | `bash "$SKILL_ROOT/scripts/pr-workflow.sh" <pr_number> [--repo owner/repo] [--watch-checks] [--full-comments]` |
| Add top-level PR comment (newline-safe) | `bash "$SKILL_ROOT/scripts/pr-comment.sh" <pr_number> --body "<text>" [--repo owner/repo]` |
| Request bot re-review deterministically | `bash "$SKILL_ROOT/scripts/pr-request-review.sh" <pr_number> [--repo owner/repo] [--note "<text>"]` |
| Mark draft PR ready (strict gates) | `bash "$SKILL_ROOT/scripts/pr-mark-ready.sh" <pr_number> [--repo owner/repo] [--watch-checks]` |
| List unresolved inline threads | `bash "$SKILL_ROOT/scripts/pr-unresolved-threads.sh" <pr_number> [--repo owner/repo] [--fail-on-unresolved]` |
| Resolve unresolved inline threads | `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --all [--author <login>] [--dry-run]` |
| Resolve specific inline threads | `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --thread-id <id> [--thread-id <id> ...] [--dry-run]` |
| Reply to inline review comment | `bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> \"<reply text>\" [--repo owner/repo]` |
| Discover remote issue templates | `bash "$SKILL_ROOT/scripts/issue-template-discover.sh" [--repo owner/repo] [--format text\|json] [--template-id <path>]` |
| Create issue with deterministic body/template flow | `bash "$SKILL_ROOT/scripts/issue-create.sh" --title \"<title>\" [--create --force-create] [--repo owner/repo] [--body-file <path> \| --body \"<text>\"] [--template-id <path>] [issue args]` |
| Squash merge a PR deterministically (auto-deletes source branch) | `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> [--repo owner/repo] [--summary \"<desc override>\"] [--admin] [--dry-run]` |
| Receipt generation | `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <base> [--pr-url <url>]` |
| Governance capability preflight | `bash "$SKILL_ROOT/scripts/gh-scope-check.sh" --repo <owner/repo> [--format text|json]` |
| Governance enforcement sequence | `bash "$SKILL_ROOT/scripts/governance-enforce.sh" [--policy <path>] --repo owner/repo [--no-write-codeowners]` |

Exception protocol:
- If you bypass a required script, include one line in your output: `Script bypass reason: <specific blocker>`.
- Valid blockers are limited to missing script capability, incompatible inputs, or script runtime failure.

Detailed routing notes: [references/SCRIPT_ROUTING.md](references/SCRIPT_ROUTING.md)

---

## Quick start flow (agent checklist)

When you are asked to “do Git work” in a repo, do this first:

1. **Detect repo context**
   - default branch name (prefer `origin/HEAD`)
   - current branch, dirty working tree, remote URL
   - existing workflow enforcement (PR template, CI, branch protections)
2. **Choose the correct playbook**
   - start work → Branching playbook
   - open PR → PR creation playbook
   - update PR → PR update playbook
   - merge PR → Merge playbook
   - release notes → Release notes playbook

Detailed checklists live in:

- [references/CHECKLISTS.md](references/CHECKLISTS.md)

Minimal deterministic command path (progressive-disclosure entrypoint):

```bash
bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output
bash "$SKILL_ROOT/scripts/setup-security.sh"
bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact
bash "$SKILL_ROOT/scripts/pr-create.sh" --title "feat(cli): add json output"
# Step 1 (required before --create): inspect labels and templates
bash "$SKILL_ROOT/scripts/pr-labels-list.sh" --repo <owner/repo>
bash "$SKILL_ROOT/scripts/pr-template-discover.sh" --repo <owner/repo>
# edit generated body file if needed, then explicitly create PR
# draft by default; pass --ready for non-draft
# bash "$SKILL_ROOT/scripts/pr-create.sh" --title "feat(cli): add json output" --create --force-create --repo <owner/repo> --label bug --label enhancement
# after checks/threads are clean:
# bash "$SKILL_ROOT/scripts/pr-mark-ready.sh" <pr_number> --repo <owner/repo>
bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number>
python3 "$SKILL_ROOT/scripts/receipt.py" --branch "$(git rev-parse --abbrev-ref HEAD)" --base origin/main
```

---

## Playbook A: Start work (branching)

### Goal

Create a correctly named branch from the default branch, without accidentally working on `main`.

### Steps

1. If working tree is dirty, stash tracked + untracked changes with deterministic metadata.
   - `scripts/start-branch.sh` handles this automatically and restores after branch switch.
   - It also auto-installs the managed pre-commit sensitive-scan hook (use `--no-install-hooks` to skip).
2. Sync the default branch:
   - `git checkout <default-branch> && git pull`
3. Create a branch:
   - `git checkout -b <type>/<short-desc>`

**Recommended helper** (handles default-branch detection + naming validation):

- `scripts/start-branch.sh`
  - Resolve as: `"$SKILL_ROOT/scripts/start-branch.sh"`

Example:

```bash
bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output
bash "$SKILL_ROOT/scripts/start-branch.sh" chore --issue 4321 --stash-name "carry-local-wip"
```

---

## Playbook B: Commit work (Conventional Commits)

### Rules

Use:

```md
<type>(<scope>): <description>

[optional body]

[optional footer]
```

- imperative mood, lowercase, no trailing period
- scope is optional but preferred when it adds clarity
- keep commits atomic and logically grouped
- run sensitive-data gate before commit:
  - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact`
- when asked to "commit worktree"/"commit things", batch commits by logical units; single all-in-one commit is exception-only (explicit request required)

See:

- [references/CONVENTIONAL_COMMITS.md](references/CONVENTIONAL_COMMITS.md)
- [assets/config/gitleaks.toml](assets/config/gitleaks.toml)

---

## Playbook C: Create a PR

### Steps (GitHub)

1. Find/link relevant issues:
   - `gh issue list --search "keyword"`
   - Use `Fixes #123` / `Closes #123` in the PR body when appropriate
2. Discover labels and templates in repo context before `--create` (deterministic step 1):
   - `bash "$SKILL_ROOT/scripts/pr-labels-list.sh" --repo <owner/repo>`
   - `bash "$SKILL_ROOT/scripts/pr-template-discover.sh" --repo <owner/repo>`
3. Use the PR template structure:
   - [assets/templates/pull-request-body.md](assets/templates/pull-request-body.md)
4. Create PR using a **body file** (avoid literal `\n` rendering):
   - `gh pr create --title "<title>" --body-file <file>`
5. Scripted deterministic create flow:
   - Draft default: `bash "$SKILL_ROOT/scripts/pr-create.sh" --title "<title>" --create --force-create --repo <owner/repo> --label <label>`
   - Explicit non-draft: add `--ready`
   - If repo has labels, pass labels explicitly via repeatable `--label` or explicit `--no-labels`.
   - If repo has multiple remote PR templates, pass `--template-id <path>` before `--create`.

Optional helper:

- `scripts/pr-create.sh` (uses remote repository PR template content when available; otherwise generates a deterministic PR body from git history; PR creation requires explicit `--create --force-create`, creates **draft** by default, and requires explicit labels when labels exist)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-create.sh"`
- `scripts/pr-labels-list.sh` (deterministically list available labels before create)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-labels-list.sh"`
- `scripts/pr-template-discover.sh` (discover/extract remote PR templates; `--template-id` required for multi-template repos before `--create`)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-template-discover.sh"`
- `scripts/pr-mark-ready.sh` (strict deterministic draft->ready transition after checks/threads pass)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-mark-ready.sh"`

---

## Playbook D: Update an existing PR (strict)

Before pushing any new commits to a PR branch:

1. Read top-level PR comments:
   - `gh pr view <number> --comments`
2. Read unresolved inline review threads:
   - `bash "$SKILL_ROOT/scripts/pr-unresolved-threads.sh" <number>`
3. Review CI checks/logs:
   - `gh pr checks <number> --watch`
4. Address/respond to every unresolved item.
   - Reply in the original thread (do NOT create a new top-level comment).
   - Classify each unresolved item as `valid/relevant` or `not applicable/invalid`.
   - For `not applicable/invalid`, reply with rationale in-thread and resolve the thread when permissions allow.
   - `pr-reply.sh` normalizes literal `\n` in reply text into real newlines.
5. If you implemented a bot suggestion or need re-review, re-tag the bot in-thread.
   - Optional trigger commands (if enabled in repo): `@codex review` then `/gemini review` (post in top-level PR Conversation comments).
   - For conversational follow-ups, use `@gemini-code-assist <question>`.
   - Preferred deterministic command: `bash "$SKILL_ROOT/scripts/pr-request-review.sh" <pr_number> [--repo owner/repo] [--note "<text>"]`
   - For manual multi-line top-level PR comments, avoid literal `\n` escapes; use `--body-file`:
     - `gh pr comment <number> --body-file <file>`

Guidance for handling automated reviewer feedback:

- [references/AUTOMATED_REVIEWERS.md](references/AUTOMATED_REVIEWERS.md)
- `scripts/pr-workflow.sh` (strict deterministic wrapper)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-workflow.sh"`
- `scripts/pr-update-body.sh` (deterministic existing PR body update helper)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-update-body.sh"`
- `scripts/pr-mark-ready.sh` (strict deterministic draft->ready transition wrapper)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-mark-ready.sh"`

Draft-ready lifecycle:
- `pr-create.sh --create` always creates draft PRs unless `--ready` is set.
- Use `pr-mark-ready.sh` after unresolved threads and required checks are green.

---

## Playbook E: Merge a PR (squash & merge)

1. Run deterministic merge wrapper:
   - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number>`
2. Wrapper merge command always includes `--delete-branch` to remove the source branch after successful merge.
3. Wrapper preconditions (default mode):
   - conversations resolved
   - required CI checks green
   - approvals present
   - PR is not draft and mergeable
4. Squash merge body omits empty optional sections and is generated deterministically with commit bullets:
   - `- <short-sha> <first-line commit subject>`
   - `## Commits` and `## Refs` are always present
5. Optional escalation path for repository admins:
   - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> --admin`
   - this passes `--admin` (while preserving `--delete-branch`) to `gh pr merge` and relaxes approval/check gates
6. After merge, emit a commit receipt:
   - `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <default-branch> --pr-url <url>`

---

## Playbook F: Draft release notes

Use:

- [assets/templates/release-notes.md](assets/templates/release-notes.md)

Optional helper (builds a skeleton from git history):

- `python3 "$SKILL_ROOT/scripts/generate-release-notes.py" --since <tag-or-sha> --version vX.Y.Z`
  - omits empty optional sections (`## New Features`, `## What's Changed`, `## Bug Fixes`, `## Breaking Changes`)
  - always emits `## Commits` and `## Refs`
  - `--include-commits` adds per-commit SHA bullets inside `## Commits`; the section is emitted regardless

---

## Playbook G: Deterministic governance reconciliation

### Goal

Enforce repository governance as desired-state policy for branch/ruleset protections, required checks, CODEOWNERS, and labels.

### Canonical policy file

- `assets/config/github-governance-policy.v1.json`
- Contract details: [references/GOVERNANCE_POLICY.md](references/GOVERNANCE_POLICY.md)

### Strict command sequence

1. Validate policy:
   - `python3 "$SKILL_ROOT/scripts/repo-governance.py" validate --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json"`
2. Plan drift (non-mutating):
   - `python3 "$SKILL_ROOT/scripts/repo-governance.py" plan --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo>`
3. Apply reconciliation (mutating):
   - `python3 "$SKILL_ROOT/scripts/repo-governance.py" apply --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo> --write-codeowners`
4. Audit final state:
   - `python3 "$SKILL_ROOT/scripts/repo-governance.py" audit --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo> --format json`

Wrapper helper:
- `bash "$SKILL_ROOT/scripts/governance-enforce.sh" --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo>`

### Bootstrap helpers

- Discover candidate required checks:
  - `bash "$SKILL_ROOT/scripts/required-checks-discover.sh" --repo <owner/repo>`
- Export existing labels:
  - `bash "$SKILL_ROOT/scripts/labels-export.sh" --repo <owner/repo>`
- Lint CODEOWNERS ordering/tokens:
  - `python3 "$SKILL_ROOT/scripts/codeowners-lint.py" --path .github/CODEOWNERS`

Operational details:
- [references/ENFORCEMENT.md](references/ENFORCEMENT.md)
- [references/GH_GOVERNANCE_RUNBOOK.md](references/GH_GOVERNANCE_RUNBOOK.md)

---

## Playbook H: Create an issue (deterministic)

1. Discover remote issue templates before creation:
   - `bash "$SKILL_ROOT/scripts/issue-template-discover.sh" --repo <owner/repo>`
2. Build or select issue body source:
   - `--body-file <path>` if pre-authored
   - `--body "<text>"` for inline deterministic content
   - if omitted, helper resolves remote template content or falls back to skill template
3. Create issue via explicit creation gate:
   - `bash "$SKILL_ROOT/scripts/issue-create.sh" --title "<title>" --create --force-create --repo <owner/repo>`
4. Multi-template repositories:
   - if multiple issue templates exist, pass `--template-id <path>` before `--create`

Helper references:
- `scripts/issue-template-discover.sh`
  - Resolve as: `"$SKILL_ROOT/scripts/issue-template-discover.sh"`
- `scripts/issue-create.sh`
  - Resolve as: `"$SKILL_ROOT/scripts/issue-create.sh"`
- `assets/templates/issue-body.md`

---

## Optional enforcement (recommended)

This skill includes ready-to-copy templates:

- **PR title lint** (Conventional Commits for squash merge title)
  - `assets/github/workflows/pr-title-lint.yml`
- **Commit message lint** (commitlint)
  - `assets/github/workflows/commitlint.yml`
- **Sensitive-data scan** (gitleaks; recommended)
  - `assets/github/workflows/sensitive-scan.yml`
- **Release automation** (optional; Conventional Commits based)
  - `assets/github/workflows/release-please.yml`

See:

- [references/ENFORCEMENT.md](references/ENFORCEMENT.md)
- [references/AUTOMATED_REVIEWERS.md](references/AUTOMATED_REVIEWERS.md)
- [references/GH_CLI_SNIPPETS.md](references/GH_CLI_SNIPPETS.md)

Template resolution policy for PR creation:
- Prefer remote repository PR templates when discoverable.
- Discovery includes single-file templates in `.github/`, repo root, and `docs/` (both `pull_request_template.md` and `PULL_REQUEST_TEMPLATE.md`) and multi-template directories in `.github/PULL_REQUEST_TEMPLATE/`, `PULL_REQUEST_TEMPLATE/`, and `docs/PULL_REQUEST_TEMPLATE/`.
- If multiple remote templates exist, `pr-create.sh --create` requires explicit `--template-id`.
- If no remote templates exist, default deterministic skill PR body generation is used.

---

## Output requirement: Commit receipts

After any push/merge operation, include a receipt like:

```markdown
- **branch `<branch-name>`**
  - `<SHA>` `<type>[(<scope>)]:` _<description>_
  - `<SHA>` `<type>[(<scope>)]:` _<description>_
```

Helper:

- `python3 "$SKILL_ROOT/scripts/receipt.py"`

Details:

- [references/RECEIPTS.md](references/RECEIPTS.md)
