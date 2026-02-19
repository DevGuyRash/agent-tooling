# Script Routing (Deterministic Dispatch)

This document defines when agents must use bundled scripts instead of ad hoc command sequences.

## Rule

If a script exists for the operation, use the script first.
Resolve script paths from the skill directory, not the target repository directory.
Set `SKILL_ROOT` to the absolute path of the `gitops-workflow` skill folder (the folder containing `SKILL.md`), then call scripts via `"$SKILL_ROOT/scripts/..."`.

Only bypass when:
- script cannot express required inputs,
- script fails for reasons outside task scope,
- repo policy requires a different command path.

When bypassing, record:
- `Script bypass reason: <specific blocker>`

## Routing table

- Branch creation:
  - `bash "$SKILL_ROOT/scripts/start-branch.sh" <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>] [--no-install-hooks]`
- Hook installation:
  - `bash "$SKILL_ROOT/scripts/install-hooks.sh" [--repo <path>] [--force]`
- Sensitive-data pre-commit gate (required before `git commit`):
  - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact [--repo <path>]`
- Sensitive-data full repo scan (CI/manual parity):
  - `bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --all --redact [--repo <path>]`
- PR creation:
  - `bash "$SKILL_ROOT/scripts/pr-create.sh" --title "<title>" [--create --force-create] [--draft] [--base <branch>] [--head <branch>]`
  - Recommended deterministic flow: run without `--create`, review/edit generated body, then run `gh pr create --body-file <file>`.
- PR hygiene snapshot:
  - `bash "$SKILL_ROOT/scripts/pr-audit.sh" <pr_number>`
- Strict PR update gate:
  - `bash "$SKILL_ROOT/scripts/pr-workflow.sh" <pr_number> [--repo owner/repo] [--watch-checks]`
- Unresolved inline thread check:
  - `bash "$SKILL_ROOT/scripts/pr-unresolved-threads.sh" <pr_number> [--repo owner/repo] [--fail-on-unresolved]`
- Resolve unresolved inline threads:
  - `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --all [--author <login>] [--dry-run]`
  - `bash "$SKILL_ROOT/scripts/pr-resolve-threads.sh" <pr_number> [--repo owner/repo] --thread-id <id> [--thread-id <id> ...] [--dry-run]`
- Inline review reply:
  - `bash "$SKILL_ROOT/scripts/pr-reply.sh" <pr_number> <comment_id> "<reply text>" [--repo owner/repo]`
- Squash merge (deterministic, required):
  - `bash "$SKILL_ROOT/scripts/pr-merge-squash.sh" <pr_number> [--repo owner/repo] [--summary "<desc override>"] [--admin] [--dry-run]`
- Receipt generation:
  - `python3 "$SKILL_ROOT/scripts/receipt.py" --branch <branch> --base <base> [--pr-url <url>]`
- Governance enforcement:
  - `bash "$SKILL_ROOT/scripts/governance-enforce.sh" [--policy <path>] [--repo owner/repo] [--no-write-codeowners]`

## Strict mode hints

- Use hook installer once per repository to enforce local blocking pre-commit scans.
- Use `--no-download` only in pinned/offline environments that preinstall `gitleaks`.
- Use `--fail-on-unresolved` when unresolved threads should block updates.
- Use `--watch-checks` when waiting for CI status transitions.
- Use governance wrapper defaults to enforce `validate -> plan -> apply -> audit` ordering.
