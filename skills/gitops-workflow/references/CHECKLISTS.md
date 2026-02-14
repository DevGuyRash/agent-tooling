# Checklists

Use these checklists to keep work consistent and auditable. If a repo already has a stricter version, follow the stricter rules.

Script-first policy:
- If a checklist step has a mapped script, use the script first.
- If you bypass the script, record: `Script bypass reason: <specific blocker>`.
- Routing reference: [SCRIPT_ROUTING.md](SCRIPT_ROUTING.md).

---

## A) Start work checklist (branching)

- [ ] `git status --porcelain` is clean (no accidental partial changes)
- [ ] you are on the default branch (`main`/`master`)
- [ ] default branch is up to date (`git pull`)
- [ ] new branch name matches allowed pattern: `<type>/<short-desc>`
- [ ] branch name is kebab-case and concise (`add-json-output`, not `AddedJsonOutput`)

Recommended:
```bash
bash scripts/start-branch.sh feat add-json-output
```

---

## B) Commit checklist (Conventional Commits)

- [ ] commit subject matches: `type(scope): description`
- [ ] subject is imperative + lowercase + no trailing period
- [ ] commit is atomic (one logical change)
- [ ] scope is used when it reduces ambiguity (e.g., `cli`, `api`, `docs`)
- [ ] tests/docs included in same commit when they are part of the same logical change

---

## C) PR creation checklist

- [ ] PR title matches Conventional Commits (important for squash merge)
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
  - `bash scripts/pr-workflow.sh <number> --watch-checks`
- [ ] Read top-level comments:
  - `gh pr view <number> --comments`
- [ ] Read unresolved inline review threads:
  - `bash scripts/pr-unresolved-threads.sh <number> --fail-on-unresolved`
- [ ] Check CI and logs:
  - `gh pr checks <number> --watch`
- [ ] Identify every unresolved request and either:
  - implement it, or
  - reply in-thread explaining why you won't (with reasoning)
- [ ] If you implemented a bot suggestion or want re-review, re-tag it in-thread.

---

## E) Merge checklist (squash & merge)

- [ ] all review conversations resolved (top-level + inline)
- [ ] all required CI checks green
- [ ] at least one approving review (unless explicitly waived)
- [ ] PR author says “ready to merge”
- [ ] branch is up to date with base (rebase if required)
- [ ] squash commit message uses required structure:
  - [assets/templates/squash-merge-message.md](../assets/templates/squash-merge-message.md)
- [ ] after merge/push, emit commit receipt:
  - `python3 scripts/receipt.py --branch <branch> --base <default-branch> --pr-url <url>`

---

## F) Release notes checklist

- [ ] follow required section order:
  - Overview → New Features → What's Changed → Bug Fixes → Breaking Changes → Commits → Refs
- [ ] omit empty sections except Overview
- [ ] keep bullets single-line where possible
- [ ] use `## Refs` as canonical place for issue links

Template:
- [assets/templates/release-notes.md](../assets/templates/release-notes.md)

---

## G) Governance enforcement checklist (strict)

- [ ] Run deterministic wrapper sequence:
  - `bash scripts/governance-enforce.sh --policy assets/config/github-governance-policy.v1.json --repo <owner/repo>`
- [ ] Confirm `validate` succeeded before apply.
- [ ] Confirm `plan` output reviewed before apply.
- [ ] Confirm `audit` has no drift after apply.
