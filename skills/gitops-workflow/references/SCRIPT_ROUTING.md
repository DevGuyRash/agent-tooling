# Script Routing (Deterministic Dispatch)

This document defines when agents must use bundled scripts instead of ad hoc command sequences.

## Rule

If a script exists for the operation, use the script first.
Resolve script paths from the skill directory, not the target repository directory.
Set `SKILL_ROOT` to the absolute path of the `gitops-workflow` skill folder (the folder containing `SKILL.md`), then call scripts via `"$SKILL_ROOT/scripts/..."`.
If you are editing `gitops-workflow` itself inside a worktree/checkout of the skill repository, set `SKILL_ROOT` from the active worktree copy under review so helper behavior matches the branch contents rather than a separate source checkout.
When you need to discover the supported top-level gitops commands or aliases, prefer `bash "$SKILL_ROOT/scripts/gitops-help.sh" --json` before loading broader docs.

Only bypass when:
- script cannot express required inputs,
- script fails for reasons outside task scope,
- repo policy requires a different command path.

When bypassing, record:
- `Script bypass reason: <specific blocker>`

## Routing table

- Help / capability discovery:
  - `bash "$SKILL_ROOT/scripts/gitops-help.sh" [--json] [--verbose] [--topic <ship|sync|doctor|branch|pr|issue|governance|all>]`
  - Prefer `--json` for agents and wrappers so routing can stay lean and avoid loading larger docs.
- Repo/tree diagnosis:
  - `bash "$SKILL_ROOT/scripts/repo-state.sh" [--repo <path>] [--json] [--no-recurse-related] [--no-fetch]`
  - Default scope is the full related tree; use `--no-recurse-related` to stay on the current repo only.
- Safe repo-state recovery:
  - `bash "$SKILL_ROOT/scripts/recover-repo-state.sh" [--repo <path>] [--json] [--no-recurse-related] [--no-detached-recovery]`
  - Default scope is the full related tree; safe sequencer/detached recovery continues automatically, rescue-grade recovery stops and reports next action.
- High-level doctor entrypoint:
  - `bash "$SKILL_ROOT/scripts/doctor.sh" [fix] [--repo <path>] [--scope current|tree] [--json] [--no-fetch] [--no-detached-recovery]`
  - `doctor` is report-first; `doctor fix` applies safe recovery/sync and reports remaining reconciliation work without creating commits, pushes, or PRs.
- Branch/worktree creation (worktree default):
  - `bash "$SKILL_ROOT/scripts/start-branch.sh" <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>] [--no-worktree] [--existing] [--no-install-hooks] [--no-detached-recovery] [--json]`
  - Default scope is the current repo only; helper refreshes refs and auto-recovers safe local sequencer/detached state before branch work.
- Non-raw worktree enforcement for an existing feature branch:
  - `bash "$SKILL_ROOT/scripts/ensure-worktree.sh" [--repo <path>] [--branch <name>] [--json]`
  - Default scope is the current repo only; helper refreshes refs and auto-recovers safe local sequencer/detached state before worktree adoption.
- Security bootstrap (hooks + CI files):
  - `bash "$SKILL_ROOT/scripts/setup-security.sh" [--repo <path>] [--force] [--no-hooks] [--no-ci] [--json]`
- Governance capability preflight (required before governance enforce):
  - `bash "$SKILL_ROOT/scripts/gh-scope-check.sh" --repo <owner/repo> [--format text|json]`
- Hook installation:
  - `bash "$SKILL_ROOT/scripts/install-hooks.sh" [--repo <path>] [--force] [--json]`
- Commit signing detection (check before committing):
  - `bash "$SKILL_ROOT/scripts/detect-signing.sh"`
- Sensitive-data pre-commit gate (required before `git commit`):
  - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact [--repo <path>]`
- Sensitive-data full repo scan (CI/manual parity):
  - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --all --redact [--repo <path>]`
- Raw in-place sync on the current branch and related tree:
  - `bash "$SKILL_ROOT/scripts/sync-raw.sh" [--repo <path>] [--json] [--no-detached-recovery] [--no-recurse-related]`
  - Recognized phrases `sync raw` and `raw sync` route here directly.
  - Default scope is the full related tree; use `--no-recurse-related` to stay on the current repo only.
  - Raw sync now behaves like a bidirectional branch sync: it fetches, fast-forwards when behind, rebases when diverged, publishes branches without upstream, pushes local commits when safe, and preserves dirty work via stash-plus-fallback restore.
  - JSON statuses distinguish fast-forward pull, push-only, rebased-and-pushed, published, deterministic fallback restore, and blocked recovery cases.
- High-level ship entrypoint:
  - `bash "$SKILL_ROOT/scripts/ship.sh" [raw|sync] [push|pr|ready] [--repo <path>] [--scope current|tree] [--json] [--no-detached-recovery]`
  - `ship` syncs first, then uses the normal branch/worktree/PR flow and reports a readiness snapshot after the PR exists; `ship raw` syncs, batches Conventional Commits, pushes in place, and reports a snapshot when a PR already exists.
  - `ship sync` is the sync-only `ship.sh` mode; it runs the raw sync stage and stops before commit, push, or PR stages.
  - `ship ready` is audit-only: it reports readiness for the current branch PR and never creates a PR or flips draft state.
- Parent/submodule tree reconciliation after sync/merge/submodule commits:
  - `bash "$SKILL_ROOT/scripts/reconcile-tree.sh" [--repo <path>] [--json] [--mode check|apply]`
  - Default scope is the full related tree; parent gitlinks remain authoritative.
- Deterministic Conventional Commit message generation:
  - `python3 "$SKILL_ROOT/scripts/commit-message.py" --type <type> [--scope <scope>] --subject "<subject>" --bullet "<line>" [--bullet "<line>" ...] [--footer "<line>" ...] [--out <path>]`
- PR creation:
  - `bash "$SKILL_ROOT/scripts/pr-labels-list.sh" [--repo owner/repo] [--format text|json]`
  - `bash "$SKILL_ROOT/scripts/pr-template-discover.sh" [--repo owner/repo] [--format text|json]`
  - `bash "$SKILL_ROOT/scripts/pr-create.sh" --title "<title>" [--create --force-create] [--ready] [--base <branch>] [--head <branch>] [--repo owner/repo] [--label <name> ... | --no-labels] [--template-id <path>]`
  - Recommended deterministic flow: (1) list labels/templates, (2) run `pr-create.sh` without `--create`, review/edit generated body, then (3) run `pr-create.sh --create --force-create ...` with explicit labels.
- Existing PR body updates:
  - `bash "$SKILL_ROOT/scripts/pr-update-body.sh" <pr_number> [--repo owner/repo] (--body-file <path> | --body "<text>") [--dry-run]`
- PR hygiene snapshot:
  - `bash "$SKILL_ROOT/scripts/pr-audit.sh" <pr_number>`
- PR readiness report:
  - `python3 "$SKILL_ROOT/scripts/pr-readiness-report.py" <pr_number> [--repo owner/repo] [--local-repo <path>] [--scope current|tree] [--watch-checks] [--json]`
  - Reports required checks, review state, and local/tree git state in one deterministic snapshot.
- Strict PR update gate:
  - `bash "$SKILL_ROOT/scripts/pr-workflow.sh" <pr_number> [--repo owner/repo] [--watch-checks] [--full-comments]`
- Top-level PR comment (deterministic; avoids literal `\n` rendering):
  - `bash "$SKILL_ROOT/scripts/pr-comment.sh" <pr_number> --body "<text>" [--repo owner/repo]`
- Bot re-review request (deterministic ordering: Codex then Gemini):
  - `bash "$SKILL_ROOT/scripts/pr-request-review.sh" <pr_number> [--repo owner/repo] [--note "<text>"]`
- Mark draft PR ready after strict gates:
  - `bash "$SKILL_ROOT/scripts/pr-mark-ready.sh" <pr_number> [--repo owner/repo] [--watch-checks]`
  - This wrapper now runs `pr-readiness-report.py` first and refuses to mutate when the draft PR is not safe to flip.
- Unresolved inline thread check:
  - `bash "$SKILL_ROOT/scripts/pr-unresolved-threads.sh" <pr_number> [--repo owner/repo] [--fail-on-unresolved]`
- Resolve unresolved inline threads:
  - `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --all [--author <login>] [--dry-run]`
  - `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --thread-id <id> [--thread-id <id> ...] [--dry-run]`
- Inline review reply:
  - `bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> --body-file <path> [--repo owner/repo]` (preferred)
  - `bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> --body "<text>" [--repo owner/repo]`
  - `bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> --body=<text> [--repo owner/repo]` for literals that begin with `--`
  - Literal `\n` in `--body` text is normalized to real newlines.
- Issue templates and creation:
  - `bash "$SKILL_ROOT/scripts/issue-template-discover.sh" [--repo owner/repo] [--format text|json] [--template-id <path>]`
  - `bash "$SKILL_ROOT/scripts/issue-create.sh" --title "<title>" [--create --force-create] [--repo owner/repo] [--body-file <path> | --body "<text>"] [--template-id <path>] [--label <name> ...] [--assignee <login> ...] [--milestone <name|number>] [--dry-run]`
- Squash merge (skeleton default; auto-deletes source branch on success):
  - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> [--repo owner/repo] [--summary "<desc override>"] [--body-file <path> | --body-out <path>] [--deterministic] [--admin] [--dry-run]`
  - Default generates a skeleton with deterministic Commits/Refs and `<!-- AGENT: -->` placeholders for prose sections. Use `--deterministic` for fully mechanical bodies (legacy).
  - Recommended flow: (1) run with `--body-out <path> --dry-run`, (2) fill placeholders with natural prose, then (3) rerun with `--body-file <path>`.
- Post-merge local cleanup:
  - `bash "$SKILL_ROOT/scripts/finish-work.sh" [--branch <name>] [--base <branch>] [--dry-run] [--no-detached-recovery] [--json]`
  - Default scope is the current repo only; helper refreshes refs and auto-recovers safe local sequencer/detached state before cleanup checks.
- Receipt generation:
  - `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <base> [--pr-url <url>]`
- Governance enforcement:
  - `bash "$SKILL_ROOT/scripts/governance-enforce.sh" [--policy <path>] --repo owner/repo [--no-write-codeowners]`

## Strict mode hints

- Use hook installer once per repository to enforce local blocking pre-commit scans.
- Use `--no-download` only in pinned/offline environments that preinstall `gitleaks`.
- Use `--fail-on-unresolved` when unresolved threads should block updates.
- Use `--watch-checks` when waiting for CI status transitions.
- Use governance wrapper defaults to enforce `validate -> plan -> apply -> audit` ordering.
