# Goal Contract: G-001 Fix Password Reset Flow

## Status

- State: active
- Created: 2026-06-06
- Source: example
- Contract hash: pending

## Objective

Fix the password reset flow so a user can request a reset email, open the reset link, set a new password, and log in with the new password.

## Intent

Restore a critical authentication flow while avoiding auth redesign or unrelated behavior changes.

## Context

Relevant area is the auth password reset path and related tests. Assume the project has an auth test command available or a relevant subset can be inferred from package scripts.

## Available Capabilities

- Skills: authoring-goals
- Plugins: goalspec
- MCP servers: none required
- Hooks: GoalSpec scope/evidence/stop hooks when enabled
- Subagents/custom agents: none required
- Project commands: relevant auth test command to be discovered from the repo

## Completeness Dimensions

This goal must cover:
- Functional behavior: request reset, open reset link, set password, log in with new password.
- Verification: regression test and relevant auth tests pass.
- Regression safety: unrelated login, signup, and session behavior remains unchanged.
- Security/config safety: no production secrets or deployment config are changed.

## Terminal State

This goal is complete when:
- A regression test covers the failing password reset path.
- The relevant auth test command exits 0.
- Existing login, signup, and session tests still pass or are reported unavailable with reason.
- No production secrets, deployment configuration, auth redesign, email provider migration, or unrelated auth behavior changed.

## Tasks

- [ ] The reset request path issues a valid, single-use reset token
  - [ ] A reset email is produced for a known account
  - [ ] Unknown accounts produce no account-existence oracle
- [ ] The reset link sets a new password that satisfies existing policy checks
  - [ ] Used and expired tokens are rejected
    - [ ] Rejection produces no information beyond invalid-or-expired
- [ ] A regression test pins the originally failing path
- [ ] Unrelated login, signup, and session behavior is demonstrably unchanged

## Verifier

Completion must be verified by:
- Reproduce the failure before the fix if possible.
- Run the password reset regression test and report the raw result.
- Run the relevant auth test command and report the raw result.

## Scope

In scope:
- Password reset request logic.
- Reset token validation.
- Password update handling.
- Auth tests related to password reset.

Out of scope:
- Authentication redesign.
- Email provider migration.
- Unrelated login, signup, or session behavior changes.
- Production secrets.
- Deployment configuration.

## Budget

- Max implementation iterations: 3
- Max changed files: 6
- Max new dependencies: 0
- Max exploration files/directories: 30
- Stop when the budget is exhausted even if incomplete.

## Give-Up Conditions

Stop and report blocked/incomplete if:
- Required email infrastructure is unavailable.
- Required third-party credentials are missing.
- The fix requires a product decision about token expiration behavior.
- The required change would alter public auth semantics outside password reset.
- The verifier cannot run in the available environment.

## Priority Order

1. Correctness
2. Minimal behavior change
3. Regression coverage
4. Simplicity

## Follow-Up Policy

Discovered adjacent work must be recorded as candidate goals, not performed, unless required for the terminal state.

## Evidence Required

Final report must include:
- Files changed
- Commands run
- Raw pass/fail results or artifact paths
- Budget used
- Remaining risks
- Follow-up candidates
