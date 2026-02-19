---
name: gitops-workflow
description: "End-to-end GitOps workflow governance and automation: branching from the default branch, Conventional Commits, PR creation/update/merge hygiene, CI gating, squash-merge message + release notes structure, and helper scripts (git + GitHub CLI). Use when creating branches/commits/PRs/releases or enforcing team Git workflow standards."
license: MIT
compatibility: "Requires git. Optional but recommended: GitHub CLI (gh). Helper scripts use bash and python3; optional jq. Designed for GitHub-hosted repos but adaptable."
metadata:
  author: DevGuyRash
  version: "1.3.0"
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
| Start branch from default branch | `bash "$SKILL_ROOT/scripts/start-branch.sh" <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>]` |
| Create PR body + PR | `bash "$SKILL_ROOT/scripts/pr-create.sh" --title \"<title>\" [--create] [--draft] [--base <branch>] [--head <branch>]` |
| PR hygiene audit | `bash "$SKILL_ROOT/scripts/pr-audit.sh" <pr_number>` |
| Strict PR workflow (comments + unresolved threads + checks) | `bash "$SKILL_ROOT/scripts/pr-workflow.sh" <pr_number> [--repo owner/repo] [--watch-checks]` |
| List unresolved inline threads | `bash "$SKILL_ROOT/scripts/pr-unresolved-threads.sh" <pr_number> [--repo owner/repo] [--fail-on-unresolved]` |
| Resolve unresolved inline threads | `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --all [--author <login>] [--dry-run]` |
| Resolve specific inline threads | `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --thread-id <id> [--thread-id <id> ...] [--dry-run]` |
| Reply to inline review comment | `bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> \"<reply text>\" [--repo owner/repo]` |
| Squash merge a PR deterministically | `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> [--repo owner/repo] [--summary \"<desc override>\"] [--admin] [--dry-run]` |
| Receipt generation | `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <base> [--pr-url <url>]` |
| Governance enforcement sequence | `bash "$SKILL_ROOT/scripts/governance-enforce.sh" [--policy <path>] [--repo owner/repo] [--no-write-codeowners]` |

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
bash "$SKILL_ROOT/scripts/pr-create.sh" --title "feat(cli): add json output" --create
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
- when asked to "commit worktree"/"commit things", batch commits by logical units; single all-in-one commit is exception-only (explicit request required)

See:

- [references/CONVENTIONAL_COMMITS.md](references/CONVENTIONAL_COMMITS.md)

---

## Playbook C: Create a PR

### Steps (GitHub)

1. Find/link relevant issues:
   - `gh issue list --search "keyword"`
   - Use `Fixes #123` / `Closes #123` in the PR body when appropriate
2. Use the PR template structure:
   - [assets/templates/pull-request-body.md](assets/templates/pull-request-body.md)
3. Create PR using a **body file** (avoid literal `\n` rendering):
   - `gh pr create --title "<title>" --body-file <file>`

Optional helper:

- `scripts/pr-create.sh` (generates a filled PR body skeleton and opens a PR)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-create.sh"`

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
5. If you implemented a bot suggestion or need re-review, re-tag the bot in-thread.

Guidance for handling automated reviewer feedback:

- [references/AUTOMATED_REVIEWERS.md](references/AUTOMATED_REVIEWERS.md)
- `scripts/pr-workflow.sh` (strict deterministic wrapper)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-workflow.sh"`

---

## Playbook E: Merge a PR (squash & merge)

1. Run deterministic merge wrapper:
   - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number>`
2. Wrapper preconditions (default mode):
   - conversations resolved
   - required CI checks green
   - approvals present
   - PR is not draft and mergeable
3. Squash merge body is generated deterministically with commit bullets:
   - `- <short-sha> <first-line commit subject>`
4. Optional escalation path for repository admins:
   - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> --admin`
   - this passes `--admin` to `gh pr merge` and relaxes approval/check gates
5. After merge, emit a commit receipt:
   - `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <default-branch> --pr-url <url>`

---

## Playbook F: Draft release notes

Use:

- [assets/templates/release-notes.md](assets/templates/release-notes.md)

Optional helper (builds a skeleton from git history):

- `python3 "$SKILL_ROOT/scripts/generate-release-notes.py" --since <tag-or-sha> --version vX.Y.Z`

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

## Optional enforcement (recommended)

This skill includes ready-to-copy templates:

- **PR title lint** (Conventional Commits for squash merge title)
  - `assets/github/workflows/pr-title-lint.yml`
- **Commit message lint** (commitlint)
  - `assets/github/workflows/commitlint.yml`
- **Release automation** (optional; Conventional Commits based)
  - `assets/github/workflows/release-please.yml`

See:

- [references/ENFORCEMENT.md](references/ENFORCEMENT.md)
- [references/AUTOMATED_REVIEWERS.md](references/AUTOMATED_REVIEWERS.md)

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
