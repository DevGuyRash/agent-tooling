# Script Routing (Deterministic Dispatch)

This document defines when agents must use bundled scripts instead of ad hoc command sequences.

## Rule

If a script exists for the operation, use the script first.
Only bypass when:
- script cannot express required inputs,
- script fails for reasons outside task scope,
- repo policy requires a different command path.

When bypassing, record:
- `Script bypass reason: <specific blocker>`

## Routing table

- Branch creation:
  - `bash scripts/start-branch.sh <type> <slug> [--issue <id>] [--base <branch>]`
- PR creation:
  - `bash scripts/pr-create.sh --title "<title>" [--create] [--draft] [--base <branch>] [--head <branch>]`
- PR hygiene snapshot:
  - `bash scripts/pr-audit.sh <pr_number>`
- Strict PR update gate:
  - `bash scripts/pr-workflow.sh <pr_number> [--repo owner/repo] [--watch-checks]`
- Unresolved inline thread check:
  - `bash scripts/pr-unresolved-threads.sh <pr_number> [--repo owner/repo] [--fail-on-unresolved]`
- Inline review reply:
  - `bash scripts/pr-reply.sh <pr_number> <comment_id> "<reply text>" [--repo owner/repo]`
- Receipt generation:
  - `python3 scripts/receipt.py --branch <branch> --base <base> [--pr-url <url>]`
- Governance enforcement:
  - `bash scripts/governance-enforce.sh [--policy <path>] [--repo owner/repo] [--no-write-codeowners]`

## Strict mode hints

- Use `--fail-on-unresolved` when unresolved threads should block updates.
- Use `--watch-checks` when waiting for CI status transitions.
- Use governance wrapper defaults to enforce `validate -> plan -> apply -> audit` ordering.
