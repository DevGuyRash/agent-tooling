# Audit Domains — New (D23–D25)

This file defines new audit domains D23–D25 covering idempotency, error
recovery, and credential safety. These address gaps in the original D1–D22
framework around runtime state, failure resilience, and security.

---

## Table of contents

- [D23: idempotency](#d23-idempotency)
- [D24: error-recovery](#d24-error-recovery)
- [D25: credential-safety](#d25-credential-safety)

---

### D23: idempotency

**Source:** Phase 1 — Environment & Build + Phase 3 — Workflow Simulation · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/idempotency_check.sh`

**What idempotency means:** Scripts and CLIs leave no residual state; re-runs
produce identical results. An agent that re-runs a script and gets different
results (because temp files, caches, or lock files were left behind) silently
corrupts its workflow. D6 checks documentation for env-var leaks across code
blocks but never checks runtime state behavior.

**Seed checks:**
- WHEN a script runs twice on the same unchanged input, THEN output SHALL be
  byte-identical.
- Scripts SHALL NOT leave temp files, lock files, or cache artifacts after
  completion.
- WHEN a script creates temp files, THEN it SHALL clean them up in a trap
  handler.
- WHEN a workflow is interrupted mid-execution, THEN residual state SHALL NOT
  cause a different result on re-run.
- WHEN a skill documents "create X," THEN re-running when X already exists
  SHALL be safe (no-op or overwrite with identical content).

**Severity:** BLOCKER — re-run produces different output with no state change.
MAJOR — temp files left behind after normal completion. MINOR — benign
leftover (log file). NIT — could add trap cleanup.

---

### D24: error-recovery

**Source:** Phase 3 — Workflow Simulation · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/error_recovery_check.sh`

**What error recovery means:** Workflows document recovery paths for
mid-workflow failures; partial-success states are detectable. D7 checks error
message *wording* but not recovery *patterns*. When a multi-step workflow
fails at step 3, can the agent safely restart from step 1? Are there
guardrails against partial completion being interpreted as full success?

**Seed checks:**
- WHEN a workflow has 3+ steps, THEN each step's success/failure SHALL be
  independently detectable (non-zero exit code, output marker, or state file).
- WHEN a step fails, the skill SHALL document whether to retry that step,
  restart from the beginning, or abort.
- WHEN partial output exists from a failed run, THEN re-running SHALL NOT
  corrupt the partial output or produce mixed old/new results.
- Scripts SHALL NOT exit 0 when a significant sub-task failed silently.
- WHEN a skill dispatches subagents, THEN the orchestrator SHALL document how
  to handle worker failure (retry, skip, abort).

**Severity:** BLOCKER — no recovery path; agent can't resume safely. MAJOR —
recovery possible but undocumented. MINOR — recovery documented for some
failure modes only. NIT — could improve recovery ergonomics.

---

### D25: credential-safety

**Source:** Phase 1 — Environment & Build + Phase 3 — Workflow Simulation · **Tier:** Agent+Script
**Script:** `<skills-file-root>/scripts/credential_check.sh`

**What credential safety means:** No secrets in committed files; no credential
leakage in error output; secure credential handling patterns. Nothing in
AGENTS.md or any pre-existing domain covers security. A script that leaks an
API key in error output (for example, printing the full curl command with an
Authorization header carrying a bearer token) is a security incident.

**Seed checks:**
- WHEN a skill directory contains files matching secret patterns (`.env`,
  `credentials.*`, `*secret*`, `*token*`, `*key*`), THEN those files SHALL be
  in `.gitignore` or SHALL NOT contain actual credentials.
- Scripts SHALL NOT echo, log, or print credentials in normal or error output.
- WHEN a script uses `set -x` (debug tracing), THEN it SHALL disable tracing
  around credential-handling sections.
- WHEN a skill accepts credentials, THEN it SHALL prefer CLI flags over
  environment variables, and SHALL document the credential flow.
- Error messages SHALL NOT include full command lines that contain credential
  flags/headers.
- Scripts SHALL NOT use `eval` on user-provided input (command injection risk).

**Severity:** BLOCKER — credentials in committed files or leaked in normal
error paths. MAJOR — `eval` on user input; credentials in verbose-only
output. MINOR — credentials via env vars when flags are possible. NIT —
could improve credential documentation.
