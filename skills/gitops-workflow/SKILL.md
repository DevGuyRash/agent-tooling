---
name: GitOps Workflow
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
compatibility: "Requires git and GitHub CLI (gh) for GitHub operations; falls back to git/curl if gh is unavailable. Helper scripts use bash and python3; optional jq. Designed for GitHub-hosted repos but adaptable."
metadata:
  author: DevGuyRash
  version: "2.0.0"
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
- commit and push raw — skip all branch/worktree/PR creation (**push-only** mode; requires **"raw"** keyword)
- `ship`, `ship raw`, `ship sync`, `doctor`, or `doctor fix` for higher-level deterministic workflow routing

---

## Prerequisites

- `git` available and the current working directory is a git repo.
- For GitHub operations: `gh` authenticated (primary tool; falls back to `git`/`curl` if unavailable).

Optional helpers:

- `python3` (for generator scripts)
- `jq` (some `gh` JSON queries are easier with it, but not required)

Sensitive scan platform note:
- local `sensitive-scan.sh` support is Linux-first; native Windows is out of scope for this skill
- use Linux, WSL, or another POSIX environment when the scan must run locally

---

## Tool priority

- **GitHub operations** (PRs, issues, checks, reviews, labels, templates, repo metadata): `gh` (GitHub CLI) is the primary tool. WHEN `gh` is not available or not authenticated THEN you SHALL fall back to `git`/`curl` targeting the GitHub REST API.
- **Local git operations** (branching, staging, committing, worktrees, history): always `git`.
- **Script dispatch**: bundled scripts first, ad-hoc command sequences fallback-only (see [Script-first dispatch](#script-first-dispatch-mandatory) below).

## Minimal Load Path

Keep the agent context narrow by loading only what the current request needs.

1. When command discovery is needed, run `bash "$SKILL_ROOT/scripts/gitops-help.sh" --json` first instead of loading large prose sections.
2. Route the request to one script.
3. Load the matching playbook or reference only when the selected script output leaves ambiguity.

Preferred short-path routing:
- `gitops-help.sh --json` is the primary capability-discovery surface for agents and wrappers; invoke it as `bash "$SKILL_ROOT/scripts/gitops-help.sh" --json`.
- `ship`, `ship raw`, `ship sync`, `ship ready`, `doctor`, and `doctor fix` should route directly to their bundled scripts with `--json`.
- `sync raw` / `raw sync` should route to `sync-raw.sh` with `--json`.
- `commit and push raw` / `push raw` should route to `ship.sh raw --json`.
- Use JSON receipts from the scripts as the primary machine-readable status surface instead of adding more natural-language policy text.

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
8. **Default merge strategy is Squash & Merge**. Generate the squash body skeleton first (deterministic Commits/Refs + agent placeholders for prose), fill the prose sections, then merge with the completed body file. Use `--deterministic` for fully mechanical bodies without placeholders.
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
- If the target repository is itself a checkout/worktree of the skill repository and the task is modifying `gitops-workflow`, prefer the copies under the active worktree/repository being edited so script behavior matches the branch under review. Use the canonical skill-source path only when it matches the active checkout or when the active repository is not modifying this skill.
- Before dispatching, resolve and keep a local variable:
  - `SKILL_ROOT=<absolute-path-to-this-skill-folder>`
  - Example placeholder: `<absolute-path>/gitops-workflow`
- Execute helpers via `"$SKILL_ROOT/scripts/..."` so they are found even when CWD is another repo.

| Task | Required script |
| --- | --- |
| Help / capability discovery | `bash "$SKILL_ROOT/scripts/gitops-help.sh" [--json] [--verbose] [--topic <ship\|sync\|doctor\|branch\|pr\|issue\|governance\|all>]` |
| Start branch (worktree default) or adopt existing | `bash "$SKILL_ROOT/scripts/start-branch.sh" <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>] [--no-worktree] [--existing] [--no-install-hooks] [--no-detached-recovery] [--json]` |
| Auto-adopt linked worktree for non-raw feature branch work | `bash "$SKILL_ROOT/scripts/ensure-worktree.sh" [--repo <path>] [--branch <name>] [--json]` |
| Bootstrap security setup in repo | `bash "$SKILL_ROOT/scripts/setup-security.sh" [--repo <path>] [--force] [--no-hooks] [--no-ci] [--json]` |
| Install managed pre-commit hook | `bash "$SKILL_ROOT/scripts/install-hooks.sh" [--repo <path>] [--force] [--json]` |
| Diagnose current repo or related tree state | `bash "$SKILL_ROOT/scripts/repo-state.sh" [--repo <path>] [--json] [--no-recurse-related] [--no-fetch]` |
| Recover safe sequencer/detached state before continuing work | `bash "$SKILL_ROOT/scripts/recover-repo-state.sh" [--repo <path>] [--json] [--no-recurse-related] [--no-detached-recovery]` |
| High-level repo/tree doctor report | `bash "$SKILL_ROOT/scripts/doctor.sh" [fix] [--repo <path>] [--scope current|tree] [--json] [--no-fetch] [--no-detached-recovery]` |
| Sensitive-data pre-commit gate | `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" [--staged] [--all] [--repo <path>] [--format <fmt>] [--redact] [--no-download]` |
| Raw in-place sync of current branch and related repo tree | `bash "$SKILL_ROOT/scripts/sync-raw.sh" [--repo <path>] [--json] [--no-detached-recovery] [--no-recurse-related]` |
| High-level ship workflow (draft-first by default; `raw` stays in place; `sync` is sync-only mode) | `bash "$SKILL_ROOT/scripts/ship.sh" [raw|sync] [push|pr|ready] [--repo <path>] [--scope current|tree] [--json] [--no-detached-recovery]` |
| Reconcile parent/submodule gitlinks and clean child checkouts | `bash "$SKILL_ROOT/scripts/reconcile-tree.sh" [--repo <path>] [--json] [--mode check|apply]` |
| Generate Conventional Commit message with mandatory bullet body | `python3 "$SKILL_ROOT/scripts/commit-message.py" --type <type> [--scope <scope>] --subject "<subject>" --bullet "<line>" [--bullet "<line>" ...] [--footer "<line>" ...] [--out <path>]` |
| List available PR labels (names + descriptions) | `bash "$SKILL_ROOT/scripts/pr-labels-list.sh" [--repo owner/repo] [--format text|json]` |
| Discover remote PR templates | `bash "$SKILL_ROOT/scripts/pr-template-discover.sh" [--repo owner/repo] [--format text|json]` |
| Create PR body + PR (draft-first) | `bash "$SKILL_ROOT/scripts/pr-create.sh" --title \"<title>\" [--create --force-create] [--ready] [--base <branch>] [--head <branch>] [--repo owner/repo] [label args] [--template-id <path>]` |
| Update existing PR body | `bash "$SKILL_ROOT/scripts/pr-update-body.sh" <pr_number> [--repo owner/repo] (--body-file <path> | --body "<text>") [--dry-run]` |
| PR hygiene audit | `bash "$SKILL_ROOT/scripts/pr-audit.sh" <pr_number>` |
| PR readiness audit (CI + review + local/tree state) | `python3 "$SKILL_ROOT/scripts/pr-readiness-report.py" <pr_number> [--repo owner/repo] [--local-repo <path>] [--scope current|tree] [--watch-checks] [--json]` |
| Strict PR workflow (metadata + unresolved threads + checks) | `bash "$SKILL_ROOT/scripts/pr-workflow.sh" <pr_number> [--repo owner/repo] [--watch-checks] [--full-comments]` |
| Add top-level PR comment (newline-safe) | `bash "$SKILL_ROOT/scripts/pr-comment.sh" <pr_number> --body "<text>" [--repo owner/repo]` |
| Request bot re-review deterministically | `bash "$SKILL_ROOT/scripts/pr-request-review.sh" <pr_number> [--repo owner/repo] [--note "<text>"]` |
| Mark draft PR ready (strict gates) | `bash "$SKILL_ROOT/scripts/pr-mark-ready.sh" <pr_number> [--repo owner/repo] [--watch-checks]` |
| List unresolved inline threads | `bash "$SKILL_ROOT/scripts/pr-unresolved-threads.sh" <pr_number> [--repo owner/repo] [--fail-on-unresolved]` |
| Resolve unresolved inline threads | `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --all [--author <login>] [--dry-run]` |
| Resolve specific inline threads | `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --thread-id <id> [--thread-id <id> ...] [--dry-run]` |
| Reply to inline review comment | `bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> (--body-file <path> | --body "<text>" | --body=<text>) [--repo owner/repo]` |
| Discover remote issue templates | `bash "$SKILL_ROOT/scripts/issue-template-discover.sh" [--repo owner/repo] [--format text|json] [--template-id <path>]` |
| Create issue with deterministic body/template flow | `bash "$SKILL_ROOT/scripts/issue-create.sh" --title \"<title>\" [--create --force-create] [--repo owner/repo] [--body-file <path> | --body \"<text>\"] [--template-id <path>] [issue args]` |
| Squash merge a PR (auto-deletes source branch) | `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> [--repo owner/repo] [--summary \"<desc override>\"] [--body-file <path> \| --body-out <path>] [--deterministic] [--admin] [--dry-run]` |
| Clean up merged branch or worktree and return to base | `bash "$SKILL_ROOT/scripts/finish-work.sh" [--branch <name>] [--base <branch>] [--dry-run] [--no-detached-recovery] [--json]` |
| Detect commit signing availability | `bash "$SKILL_ROOT/scripts/detect-signing.sh"` |
| Receipt generation | `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <base> [--pr-url <url>]` |
| Governance capability preflight | `bash "$SKILL_ROOT/scripts/gh-scope-check.sh" --repo <owner/repo> [--format text|json]` |
| Governance enforcement sequence | `bash "$SKILL_ROOT/scripts/governance-enforce.sh" [--policy <path>] --repo owner/repo [--no-write-codeowners]` |

Exception protocol:
- If you bypass a required script, include one line in your output: `Script bypass reason: <specific blocker>`.
- Valid blockers are limited to missing script capability, incompatible inputs, or script runtime failure.

Detailed routing notes: [references/SCRIPT_ROUTING.md](references/SCRIPT_ROUTING.md)

Default scope heuristics:
- `repo-state.sh`, `recover-repo-state.sh`, `sync-raw.sh`, and `reconcile-tree.sh` inspect the full related tree by default.
- `start-branch.sh`, `ensure-worktree.sh`, commit/push flows, and `finish-work.sh` stay on the current repo by default unless the user explicitly asks for root/tree/all behavior.
- Parent gitlinks are authoritative for reconciliation; branch-name matching is only a recovery/diagnostic hint.

---

## Quick start flow (agent checklist)

When you are asked to “do Git work” in a repo, do this first:

1. **Detect repo context**
   - default branch name (prefer `origin/HEAD`)
   - current branch, dirty working tree, remote URL
   - current-branch PR context via `gh pr view --json number,title,state,baseRefName,headRefName,url` when `gh` is available and the branch already has a PR; do not infer unsupported `gh pr status --json` fields
   - existing workflow enforcement (PR template, CI, branch protections)
2. **Choose the correct playbook**
   - start work → Branching playbook (A)
   - commit work → Commit playbook (B)
   - open PR → PR creation playbook (C)
   - update PR → PR update playbook (D)
   - merge PR → Merge playbook (E)
   - release notes → Release notes playbook (F)
   - `sync raw` / `raw sync` / `ship sync` / commit and push **raw** → Raw-mode playbook (I) — `ship sync` is sync-only; other raw wording continues through the requested raw steps

Detailed checklists live in:

- [references/CHECKLISTS.md](references/CHECKLISTS.md)

Recommended repo-context probe order:

```bash
git symbolic-ref --short refs/remotes/origin/HEAD
git rev-parse --abbrev-ref HEAD
git status --short
git remote get-url origin
# If GitHub CLI is available and the current branch already has a PR:
gh pr view --json number,title,state,baseRefName,headRefName,url
```

If `gh pr view` reports that no pull request exists for the current branch,
continue without PR metadata and move to the relevant playbook.

Minimal deterministic command path (progressive-disclosure entrypoint):

```bash
bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output
bash "$SKILL_ROOT/scripts/ensure-worktree.sh" --json
# or stay in current checkout instead of creating a worktree:
# bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output --no-worktree
bash "$SKILL_ROOT/scripts/setup-security.sh"
bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact
bash "$SKILL_ROOT/scripts/pr-create.sh" --title "feat(cli): add json output"
# Step 1 (required before --create): inspect labels and templates
bash "$SKILL_ROOT/scripts/pr-labels-list.sh" --repo <owner/repo>
bash "$SKILL_ROOT/scripts/pr-template-discover.sh" --repo <owner/repo>
# edit generated body file if needed, then explicitly create PR
# draft by default; pass --ready for non-draft
# bash "$SKILL_ROOT/scripts/pr-create.sh" --title "feat(cli): add json output" --create --force-create --repo <owner/repo> --label bug --label enhancement
# audit readiness first:
# python3 "$SKILL_ROOT/scripts/pr-readiness-report.py" <pr_number> --repo <owner/repo> --watch-checks --json
# then, only when the report is clear:
# bash "$SKILL_ROOT/scripts/pr-mark-ready.sh" <pr_number> --repo <owner/repo> --watch-checks
# draft merge body for optional edits:
# bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> --body-out /tmp/squash-body.md --dry-run
# edit /tmp/squash-body.md if desired, then:
bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> [--body-file /tmp/squash-body.md]
python3 "$SKILL_ROOT/scripts/receipt.py" --branch "$(git rev-parse --abbrev-ref HEAD)" --base origin/main
# after confirming merge landed on main and remote branch is gone:
# bash "$SKILL_ROOT/scripts/finish-work.sh"
```

---

## Playbook A: Start work (worktree by default)

### Goal

Create a correctly named branch from the default branch, without accidentally working on `main`. Default behavior creates a clean linked worktree at `<repo>.worktrees/<type>/<slug>` (GitKraken-compatible layout); add `--no-worktree` to stay in the current checkout instead. For later non-raw work on an existing feature branch, run `ensure-worktree.sh` so the workflow auto-adopts the linked worktree instead of continuing from the main checkout.

### Steps

1. If working tree is dirty:
   - **Worktree mode (default):** dirty files are automatically migrated to the new worktree; the main checkout is restored to a clean state.
   - **Branch mode (`--no-worktree`):** tracked + untracked changes are stashed with deterministic metadata and restored after branch switch.
   - `scripts/start-branch.sh` handles both cases automatically.
   - It also auto-installs the managed pre-commit sensitive-scan hook (use `--no-install-hooks` to skip).
   - Before branch discovery, the helper refreshes local refs when `origin` exists and auto-recovers safe sequencer/detached state; rescue-grade recovery still stops for review.
2. Sync the default branch for the mode you are using:
   - branch mode: `git checkout <default-branch> && git pull`
   - linked worktree mode: let `start-branch.sh` resolve from the default branch without switching the current checkout
3. Create either:
   - a linked worktree at `<main-checkout>.worktrees/<type>/<slug>` (default), or
   - a local branch in the current checkout when `--no-worktree` is passed.
4. To adopt an existing branch instead of creating a new one, use `--existing`.
5. When a non-raw workflow starts on a feature branch that is not already in a linked worktree, run `bash "$SKILL_ROOT/scripts/ensure-worktree.sh" --json` and continue from the returned `path`.

**Recommended helper** (handles default-branch detection + naming validation):

- `scripts/start-branch.sh`
  - Resolve as: `"$SKILL_ROOT/scripts/start-branch.sh"`

Example:

```bash
bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output
bash "$SKILL_ROOT/scripts/start-branch.sh" chore --issue 4321 --stash-name "carry-local-wip"
bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output --no-worktree
bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output --existing
```

---

## Playbook B: Commit work (Conventional Commits)

### Rules

Use:

```md
<type>(<scope>): <description>

<bullet-list body>

[optional footer]
```

- imperative mood, lowercase, no trailing period
- scope is optional but preferred when it adds clarity
- keep commits atomic and logically grouped
- you SHALL include a mandatory bullet-list body explaining **why** the change was made; before writing commits, check `git log --oneline -10` and adapt to the project's conventions (see [references/CONVENTIONAL_COMMITS.md](references/CONVENTIONAL_COMMITS.md) for body guidelines)
- use `python3 "$SKILL_ROOT/scripts/commit-message.py" ...` when you need a deterministic commit body skeleton
- run sensitive-data gate before commit:
  - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact`
- when asked to "commit worktree"/"commit things", batch commits by logical units; single all-in-one commit is exception-only (explicit request required)

See:

- [references/CONVENTIONAL_COMMITS.md](references/CONVENTIONAL_COMMITS.md)
- [assets/config/gitleaks.toml](assets/config/gitleaks.toml)

### Commit signing

WHEN committing, the agent MAY run `detect-signing.sh` to diagnose whether signing is available:

- `bash "$SKILL_ROOT/scripts/detect-signing.sh"`

WHEN a commit fails because signing is unavailable THEN you SHALL surface the workflow helper text that explains an unsigned retry exists and that the user can be asked whether to enable it.

WHEN the user has explicitly enabled `GITOPS_ALLOW_UNSIGNED_COMMIT_RETRY=1` THEN you MAY retry the failed commit once with `commit.gpgsign=false`.

WHEN signing is not configured (exit code 2) THEN you SHALL commit normally without signing flags.

**Recommended long-term fix:** configure SSH agent forwarding so signing keys are available on remote hosts. For 1Password SSH agent, add `ForwardAgent yes` to the remote host in `~/.ssh/config`. For GPG, use `RemoteForward` of the GPG agent socket. See [1Password SSH agent forwarding docs](https://developer.1password.com/docs/ssh/agent/forwarding/) and [GnuPG agent forwarding wiki](https://wiki.gnupg.org/AgentForwarding).

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
   - If multiple local/remote PR templates are discovered, pass `--template-id <id>` before `--create`.

Optional helper:

- `scripts/pr-create.sh` (prefers local checkout PR templates, then remote repository templates, and augments the selected template with generated reviewer context; otherwise renders the skill fallback PR template; PR creation requires explicit `--create --force-create`, creates **draft** by default, and requires explicit labels when labels exist)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-create.sh"`
- `scripts/pr-labels-list.sh` (deterministically list available labels before create)
  - Resolve as: `"$SKILL_ROOT/scripts/pr-labels-list.sh"`
- `scripts/pr-template-discover.sh` (discover/extract local checkout PR templates first, then remote PR templates when repo context is available; `--template-id` required for multi-template repos before `--create`)
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
   - `pr-reply.sh` normalizes literal `\n` in `--body` text into real newlines.
   - Prefer `--body-file` for replies containing complex markdown or shell metacharacters.
   - If reply text must start with `--`, use `--body=<text>` or `--body-file`.
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
- Use `ship ready` or `pr-readiness-report.py` for a non-mutating readiness audit, then use `pr-mark-ready.sh` only when the report is clear.

---

## Playbook E: Merge a PR (squash & merge)

1. Generate the squash body skeleton (default: agent placeholders for prose + deterministic Commits/Refs):
   - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> --body-out /tmp/squash-body.md --dry-run`
2. Fill the `<!-- AGENT: -->` placeholders in the body file with natural prose describing what changed, new features, bug fixes, and breaking changes. Remove sections that don't apply. The `## Commits` and `## Refs` sections are already filled deterministically — leave them as-is.
3. Merge with the completed body:
   - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> --body-file /tmp/squash-body.md`
4. Wrapper merge command always includes `--delete-branch` to remove the source branch after successful merge.
5. Wrapper preconditions (default mode):
   - conversations resolved
   - required CI checks green
   - approvals present
   - PR is not draft and mergeable
6. For repos that prefer fully mechanical bodies (no agent prose), use `--deterministic`:
   - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> --deterministic`
7. Optional escalation path for repository admins:
   - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> --admin`
   - this passes `--admin` (while preserving `--delete-branch`) to `gh pr merge` and relaxes approval/check gates
8. After merge, emit a commit receipt:
   - `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <default-branch> --pr-url <url>`
9. After the receipt, clean up local state:
   - `bash "$SKILL_ROOT/scripts/finish-work.sh"`
   - this refuses cleanup until the remote branch is gone and the change is confirmed on the base branch
10. If the repo has its own squash merge template, use that template instead of the skill's skeleton.

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

## Playbook I: Raw mode (sync-only or commit/push raw)

### Goal

Run explicit raw in-place work on the current branch without creating branches or worktrees. Sync-only raw flows stop after raw sync; raw commit/push flows continue through the requested commit and push steps.

### Trigger

This playbook handles explicit raw in-place flows. **"ship sync"** is the sync-only `ship.sh` mode and stops after the raw sync step. Other raw wording such as **"sync raw"**, **"raw sync"**, **"commit and push raw"**, **"push raw"**, **"raw push"**, or **"ship raw"** continues through the requested raw commit/push steps. Without raw wording, normal feature-branch work first auto-adopts the linked worktree when needed, then continues with commit/push/update steps.

WHEN the user says **"ship sync"** THEN you SHALL run `bash "$SKILL_ROOT/scripts/ship.sh" sync ...` and SHALL NOT continue into commit, push, or PR steps after the raw sync stage.

WHEN the user includes **"raw"** in a sync/commit/push request THEN you SHALL use this playbook.

WHEN the user says "commit and push" without "raw" THEN you SHALL follow the normal flow:
- on the default branch → Playbook A (create worktree/branch first)
- on a feature branch not in a worktree → auto-adopt the linked worktree for the branch, then commit and push
- on a feature branch in a worktree → Playbook B (commit), then push

### Steps

1. Detect repo context (same as Quick Start step 1).
2. For sync requests, use `bash "$SKILL_ROOT/scripts/sync-raw.sh"` and keep every repo on its current branch.
   - If the original wording was **"ship sync"**, run the sync-only `ship.sh` mode and stop after this step.
   - Raw sync inspects the full related tree by default; use `--no-recurse-related` to stay on the current repo only.
   - Before syncing, the helper refreshes local refs when `origin` exists and auto-recovers safe sequencer/detached state; rescue-grade recovery still stops for review.
   - When a repo is dirty, raw sync may stash tracked + untracked changes, integrate upstream history, and then restore the dirty tree.
   - When direct stash replay conflicts after integration, raw sync resets that failed replay attempt and falls back to a deterministic union-merge restore when safe.
   - When the branch is behind only, raw sync fast-forwards from upstream.
   - When the branch has diverged, raw sync rebases onto upstream by default and then pushes when needed.
   - When the branch has local commits but no upstream, raw sync publishes the branch and sets upstream.
   - When the dirty-tree restore is not safe or history integration fails, raw sync preserves the stash and reports a blocked state.
3. Run sensitive-data gate:
   - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact`
4. Create batched Conventional Commits with mandatory bullet-list bodies (per Playbook B).
5. Check signing availability:
   - `bash "$SKILL_ROOT/scripts/detect-signing.sh"`
   - WHEN signing is configured but unavailable (exit 1) THEN you SHALL commit with `--no-gpg-sign` and warn the user.
6. Push to current branch: `git push`
7. Emit commit receipt:
   - `python3 "$SKILL_ROOT/scripts/receipt.py" --branch "$(git rev-parse --abbrev-ref HEAD)" --base <default-branch>`

WHEN raw mode is active THEN you SHALL NOT create branches, worktrees, or PRs.

WHEN raw mode continues into commit/push steps THEN you SHALL still follow Conventional Commits, the sensitive-data gate, and receipts.

High-level shortcuts:
- `ship` syncs the current scope, batches commits in a linked worktree when needed, pushes, and stops at a draft PR by default.
- `ship ready` audits the current branch PR readiness only; it does not create a PR or mark one ready.
- `ship raw` keeps work on the current branch, syncs in place, batches Conventional Commits, and pushes without branch/worktree/PR creation.
- `ship sync` is the sync-only `ship.sh` mode; it stops after the in-place raw sync path.
- `doctor` reports repo and related-tree health.
- `doctor fix` applies safe recovery and sync, then reports remaining reconciliation work without creating commits, pushes, or PRs.

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
- Prefer local checkout PR templates when present; otherwise use remote repository PR templates when discoverable.
- Discovery includes single-file templates in `.github/`, repo root, and `docs/` (both `pull_request_template.md` and `PULL_REQUEST_TEMPLATE.md`) and multi-template directories in `.github/PULL_REQUEST_TEMPLATE/`, `PULL_REQUEST_TEMPLATE/`, and `docs/PULL_REQUEST_TEMPLATE/`.
- If multiple discovered templates exist, `pr-create.sh --create` requires explicit `--template-id`.
- If no repo template exists, the skill fallback PR template is rendered with generated reviewer context.

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
