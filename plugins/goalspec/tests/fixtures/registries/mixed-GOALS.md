# GOALS.md

This is a registry, not an execution target.

## Ready

### G-001: Fix password reset test failure

- Status: ready
- Type: bugfix
- Terminal state: password reset regression test passes and related auth tests still pass
- Verifier: `pytest tests/auth/test_password_reset.py`
- Scope: auth password reset logic and tests
- Risk: low
- Depends on: none
- Contract: examples/contracts/G-001-fix-password-reset.md

## Conditional

### G-002: Improve onboarding

- Status: conditional
- Missing: target flow, success metric, verifier, and scope
- Suggested repair: choose one finite onboarding flow and define a checklist or metric
- Risk: high
- Depends on: none

## Blocked / Not Launchable

### G-003: Keep dependencies up to date

- Status: not-launchable
- Reason: maintenance loop and moving target
- Repair: freeze package set and target date
- Risk: extreme
- Depends on: none

## Ready

### G-004: Document required environment variables

- Status: ready
- Type: docs
- Terminal state: README includes required environment variables, defaults, examples, and validation command
- Verifier: human review checklist plus setup command if available
- Scope: README and config docs
- Risk: low
- Depends on: none
- Contract: pending
