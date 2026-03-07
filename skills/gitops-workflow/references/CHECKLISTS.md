# Checklists

Use these checklists to keep work consistent and auditable. If a repo already has a stricter version, follow the stricter rules.

Script-first policy:
- If a checklist step has a mapped script, use the script first.
- If you bypass the script, record: `Script bypass reason: <specific blocker>`.
- Routing reference: [SCRIPT_ROUTING.md](SCRIPT_ROUTING.md).

Set script root once when running commands from this checklist:

```bash
SKILL_ROOT=<absolute-path-to-gitops-workflow>
```

---

## A) Start work checklist (branch or worktree)

- [ ] if branch mode worktree is dirty, start helper auto-stashes tracked + untracked and restores safely
- [ ] branch helper auto-installs managed pre-commit hook unless `--no-install-hooks` is used
- [ ] branch mode starts from an up-to-date default branch checkout (`main`/`master`)
- [ ] linked worktree mode may stay on the current checkout; helper resolves from the default branch without switching the active worktree
- [ ] new branch name matches allowed pattern: `<type>/<short-desc>`
- [ ] branch name is kebab-case and concise (`add-json-output`, not `AddedJsonOutput`)
- [ ] if `<slug>` is omitted without `--issue`, the helper default is `wip-<YYYYMMDD-HHMMSS>-<HEAD8>` when `HEAD` exists
- [ ] if using linked worktree mode, target path is `<main-checkout>.worktrees/<type>/<short-desc>`

Recommended:
```bash
bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output
bash "$SKILL_ROOT/scripts/start-branch.sh" chore --issue 789 --stash-name "carry-local-wip"
bash "$SKILL_ROOT/scripts/start-branch.sh" feat add-json-output --worktree
```

---

## B) Commit checklist (Conventional Commits)

- [ ] run sensitive-data gate on staged changes before commit:
  - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact`
- [ ] if needed, install managed hook once per repo:
  - `bash "$SKILL_ROOT/scripts/install-hooks.sh" --repo <path>`
- [ ] commit subject matches: `type(scope): description`
- [ ] subject is imperative + lowercase + no trailing period
- [ ] commit is atomic (one logical change)
- [ ] scope is used when it reduces ambiguity (e.g., `cli`, `api`, `docs`)
- [ ] tests/docs included in same commit when they are part of the same logical change
- [ ] if asked to "commit worktree"/"commit changes", split into batched Conventional Commits by logical unit
- [ ] do not use one catch-all commit unless user explicitly asks for a single commit
- [ ] if scanner allowlist/config is changed, include explicit rationale in commit/PR description

---

## C) PR creation checklist

- [ ] PR title matches Conventional Commits (important for squash merge)
- [ ] Labels discovered and explicitly chosen before create:
  - `bash "$SKILL_ROOT/scripts/pr-labels-list.sh" --repo <owner/repo>`
- [ ] Remote PR templates discovered before create:
  - `bash "$SKILL_ROOT/scripts/pr-template-discover.sh" --repo <owner/repo>`
- [ ] If creating PR via script, draft is default unless `--ready` is explicitly passed.
- [ ] PR body includes:
  - summary
  - what changed
  - how tested
  - breaking changes (if any)
  - refs/issues (closing keywords if appropriate)
- [ ] bots/reviewers are tagged per repo conventions (at end of PR body)

Recommended:
- Use [assets/templates/pull-request-body.md](../assets/templates/pull-request-body.md)

---

## D) PR update checklist (strict)

Before pushing *any* updates to a PR:

- [ ] Run strict PR wrapper first:
  - `bash "$SKILL_ROOT/scripts/pr-workflow.sh" <number> --watch-checks`
  - add `--full-comments` only when you explicitly need full comment bodies
- [ ] Read top-level comments:
  - `gh pr view <number> --comments`
- [ ] Read unresolved inline review threads:
  - `bash "$SKILL_ROOT/scripts/pr-unresolved-threads.sh" <number> --fail-on-unresolved`
- [ ] Check CI and logs:
  - `gh pr checks <number> --watch`
- [ ] Identify every unresolved request and either:
  - implement it, or
  - reply in-thread explaining why you won't (with reasoning)
- [ ] For each unresolved item, classify:
  - `valid/relevant`: implement or provide a concrete in-thread response
  - `invalid/not applicable`: reply with rationale in-thread, then resolve thread when permissions allow
- [ ] If you implemented a bot suggestion or want re-review, re-tag it in-thread.
  - For Gemini full review use `/gemini review` in top-level PR Conversation comments.

---

## H) Issue creation checklist (deterministic)

- [ ] discover remote issue templates first:
  - `bash "$SKILL_ROOT/scripts/issue-template-discover.sh" --repo <owner/repo>`
- [ ] if multiple templates are found and creating issue, pass `--template-id <path>`
- [ ] body source is deterministic:
  - `--body-file <path>`, or
  - `--body "<text>"`, or
  - helper-generated body (remote template or skill fallback)
- [ ] create using explicit gate:
  - `bash "$SKILL_ROOT/scripts/issue-create.sh" --title "<title>" --create --force-create --repo <owner/repo>`

---

## E) Merge checklist (squash & merge)

- [ ] all review conversations resolved (top-level + inline)
- [ ] all required CI checks green
- [ ] at least one approving review (unless explicitly waived)
- [ ] PR author says “ready to merge”
- [ ] branch is up to date with base (rebase if required)
- [ ] run deterministic merge helper:
  - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <number>`
- [ ] confirm source branch is deleted by helper (`--delete-branch`) unless merge fails.
- [ ] if you want to polish the squash body, generate a draft first:
  - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <number> --body-out /tmp/squash-body.md --dry-run`
  - edit `/tmp/squash-body.md`, then rerun with `--body-file /tmp/squash-body.md`
- [ ] squash commit body includes `## Commits` bullets:
  - each bullet is `<short-sha> <first-line commit subject>`
- [ ] if emergency admin merge is required, use:
  - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <number> --admin`
- [ ] after merge/push, emit commit receipt:
  - `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <default-branch> --pr-url <url>`
- [ ] after merge, run local cleanup:
  - `bash "$SKILL_ROOT/scripts/finish-work.sh"`

---

## F) Release notes checklist

- [ ] follow required section order:
  - Overview → New Features → What's Changed → Bug Fixes → Breaking Changes → Commits → Refs
- [ ] omit empty optional sections; keep `Overview`, `Commits`, and `Refs`
- [ ] keep bullets single-line where possible
- [ ] use `## Refs` as canonical place for issue links

Template:
- [assets/templates/release-notes.md](../assets/templates/release-notes.md)

---

## G) Governance enforcement checklist (strict)

- [ ] Verify governance GitHub capabilities deterministically:
  - `bash "$SKILL_ROOT/scripts/gh-scope-check.sh" --repo <owner/repo>`
- [ ] Run deterministic wrapper sequence:
  - `bash "$SKILL_ROOT/scripts/governance-enforce.sh" --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo>`
- [ ] Confirm `validate` succeeded before apply.
- [ ] Confirm `plan` output reviewed before apply.
- [ ] Confirm `audit` has no drift after apply.
