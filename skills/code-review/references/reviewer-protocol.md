# Reviewer Protocol (Fallback Reference)

This document is a self-contained fallback for when `mpcr protocol` is unavailable.
IF `mpcr protocol` works, you SHALL use it instead — it serves phase-appropriate guidance just-in-time.

## Workflow overview

1. **Register** with mpcr, then iterate through 6 phases.
2. At each phase, you SHALL update mpcr status and produce the required artifacts.
3. Scale report depth to change complexity (compact/standard/full).

## Phase 1: Ingestion

You SHALL read the diff and surrounding context. You SHALL produce a change inventory:
- Files touched, approximate churn, change intent (why).
- Contract surfaces affected: APIs, schemas, CLI args, config, DB migrations.
- 1-3 depth targets: highest-risk code areas.
- Repo conventions, lints, CI constraints.

You SHALL resolve context autonomously:
- WHEN a git hosting CLI is available (e.g., `gh`, `glab`), you SHALL check for associated PRs/MRs.
- You SHALL derive acceptance criteria from PR/MR description, commits, or diff. Mark [Assumed] if inferred.
- You SHALL NOT ask the user for context you can discover programmatically.
- You MAY spawn explorer subagents for context gathering if your assigned scope is large.

`mpcr reviewer update --status IN_PROGRESS --phase INGESTION`

## Phase 2: Domain Coverage

You SHALL classify your assigned domain(s) for the change.

### Specialist agents (one domain assigned)
Determine if your domain is In-scope or Out-of-scope. If Out-of-scope, state why and produce a minimal packet.

### Generalist agents (fresh-eyes, holistic-integrator)
Classify all seed domains plus any discovered. For each: In-scope, Out-of-scope (state why), or Unknown (note gap).
Mark at least 3 In-scope for non-trivial changes.

### Seed domains

| # | Domain | Defend that... | Seed challenges |
|---|--------|---------------|-----------------|
| 1 | Architecture | design is justified, simple, consistent | over-abstraction, separation of concerns, simpler alternatives |
| 2 | Contracts | consumers unbroken across upgrades/rollbacks | API surfaces, mixed-version compat, error format stability |
| 3 | Data integrity | data is never silently lost, corrupted, or reordered | write ordering, partial failure, encoding round-trips |
| 4 | Error handling | every error path is reachable, tested, and safe | missing catches, swallowed errors, resource leaks on error |
| 5 | Security | no untrusted input reaches a privileged operation unvalidated | injection, auth bypass, SSRF, path traversal, secret exposure |
| 6 | Concurrency | shared state is correctly synchronized under all interleavings | data races, deadlock, atomicity violations |
| 7 | Performance | no regression under realistic and adversarial workloads | O(n^2) paths, unbounded allocations, missing pagination |
| 8 | Observability | failures are diagnosable from logs/metrics/traces alone | silent failures, missing context, metric cardinality |
| 9 | Testing | tests defend the contract, not the implementation | missing edge cases, brittle mocks, coverage gaps |
| 10 | Documentation | docs match the code and cover all public surfaces | stale docs, missing examples, undocumented error codes |
| 11 | Dependencies | third-party risk is bounded and auditable | version pinning, license compliance, transitive vulnerabilities |
| 12 | Supply chain security | build pipeline, artifact provenance, and dependency resolution are tamper-proof | dependency confusion, typosquatting, compromised build scripts, unsigned artifacts, phantom dependency injection |
| 13 | Authentication & authorization | identity verification and access control are correct under all code paths | privilege escalation, broken access control, token/session mismanagement, insecure defaults, missing re-auth on sensitive ops |
| 14 | Cryptography & secrets | all cryptographic usage is correct, current, and secrets are never exposed | weak algorithms, hardcoded secrets, insufficient entropy, improper key management, nonce reuse, timing side-channels |
| 15 | Input validation & injection | every external input boundary enforces strict validation before processing | SQL/NoSQL/command/LDAP injection, XSS, SSRF, template injection, header injection, deserialization attacks |
| 16 | Infrastructure & runtime security | deployment configuration and runtime environment enforce least privilege | container escapes, misconfigured network policies, overly permissive IAM/RBAC, exposed debug endpoints, insecure defaults |
| 17 | Data protection & privacy | sensitive data is classified, encrypted at rest/in-transit, and access-logged | PII leakage, missing encryption, excessive data collection, broken anonymization, missing audit trails, regulatory violations |

These are seeds. You SHALL also discover additional domains specific to the codebase.

### Domain Ledger

You SHALL produce a machine-parseable Domain Ledger:

| Domain | Scope | Theorems | Disproofs | Findings | Defended |
|--------|-------|----------|-----------|----------|----------|
| <name> | In-scope / Out-of-scope | N | N | N | N |

`mpcr reviewer update --phase DOMAIN_COVERAGE`

## Phase 3: Theorem Generation

For each In-scope domain, you SHALL generate must-prove theorems:
- Concrete, falsifiable claims referencing specific code locations (file:line).
- At least 2 theorems per In-scope domain.
- Theorems SHALL be disprovable — not truisms.
- Each theorem SHALL reference a concrete `file:line` and a specific invariant.

Anti-laziness:
- Restating the function signature is NOT a theorem.
- "The function does what it says" is NOT a theorem.
- Theorems SHALL make claims about BEHAVIOR under specific conditions.

`mpcr reviewer update --phase THEOREM_GENERATION`

## Phase 4: Adversarial Proofs

For each theorem, you SHALL attempt concrete disproof:
1. Construct a SPECIFIC scenario/input that would violate the theorem.
2. Trace the code path. Record outcome:
   - DEFENDED: disproof failed; code handles it correctly.
   - FINDING: disproof succeeded; classify severity.

Severity: BLOCKER (must fix) > MAJOR (should fix) > MINOR (improvement) > NIT (style).

### Critical-issue escalation

WHEN your domain involves security, data integrity, authentication, cryptography, injection, or privacy:
- You SHALL apply a HIGHER disproof standard: at least 3 disproof attempts per theorem (not 1).
- For each attempt, vary the attack vector:
  1. **Direct exploitation**: the simplest, most obvious attack.
  2. **Indirect/chained exploitation**: combining multiple steps or different entry points.
  3. **Edge-case/boundary exploitation**: malformed input, race conditions, integer limits, encoding tricks, null bytes.
- BLOCKER findings in security-adjacent domains SHALL include:
  - A concrete proof-of-concept scenario (specific input bytes/sequence).
  - The precise code path traced from entry to impact.
  - Impact assessment: what an attacker gains.
  - Exploitability rating: trivial / moderate / hard.

### Grounding requirements for ALL findings

Every finding SHALL meet ALL of these criteria:
1. **Anchor exists**: The `file:line` exists in the current codebase.
2. **Scenario is concrete**: Specific input values, not "a malicious input."
3. **Code path is traced**: Exact function call sequence from entry to the vulnerable line.
4. **Impact is stated**: What goes wrong (crash, data loss, breach, wrong output).
5. **Fix is actionable**: Implementable without further research.

Anti-laziness:
- "I reviewed the code and it looks fine" is NOT a valid disproof attempt.
- You SHALL describe the SPECIFIC input, sequence, or condition you tested.
- You SHALL trace at least the critical path for each disproof.
- WHEN disproof fails, explain WHY the code correctly handles the scenario.
- "This function could be vulnerable to X" is NOT a finding without a concrete exploit path.

Saturation rule: stop when 3 consecutive disproof attempts fail (5 for security-adjacent domains).

WHEN tests exist that are relevant, you SHALL run them to validate your proofs.

`mpcr reviewer update --phase ADVERSARIAL_PROOFS`

## Phase 5: Synthesis

You SHALL compile findings. For each FINDING: severity, title, anchor (file:line), claim, disproof scenario, evidence, recommendation, verification plan. ALL fields required.
For each DEFENDED theorem: anchor, theorem statement, disproof attempt, evidence, confidence.
You SHALL update your Domain Ledger with final counts.
You SHALL note residual risk: areas with insufficient coverage.

`mpcr reviewer update --phase SYNTHESIS`

## Phase 6: Report Writing

Select template scale based on change size:

### Compact (< 100 lines, single concern)
Summary + Domain Ledger + Findings + Defended Proofs + Residual Risk.

### Standard (medium changes)
Add: full Domain Ledger with rationale, structured findings with full evidence.

### Full (large / high-risk)
All sections: Change Inventory, Acceptance Criteria, Domain Ledger, Theorems, Findings (full format), Defended Proofs table, Residual Risk, Verification Plan.

You SHALL finalize:
```
mpcr reviewer finalize --verdict APPROVE|REQUEST_CHANGES|BLOCK \
  --blocker N --major N --minor N --nit N --report-file report.md
```

Finalize artifact rules:
- WHEN `--report-file` is provided, mpcr moves that file into the canonical session report path by default.
- IF you need to preserve the source file, pass `--copy-report-input`.
- IF `--report-file` is omitted, pipe report markdown via stdin.
- Parent finalize auto-closes unresolved child reviews by default (`CANCELLED`).
- If you need strict failure when children remain open, pass `--no-auto-close-children`.

## Non-negotiable rules

1. No ungrounded claims. Every finding SHALL have an evidence anchor (file:line or function).
2. Adversarial by default. You SHALL attempt to disprove every claim before accepting it.
3. Concrete scenarios only. "This could be a problem" is NOT a finding. Show the input/sequence.
4. Saturation stop. You SHALL NOT pad findings. Stop when you stop finding issues.
5. Scale to change. A typo fix does not need 11 domain sections.
6. Domain Ledger required. Every report SHALL include a machine-parseable Domain Ledger.

## mpcr quick reference

```
mpcr reviewer register --target-ref <REF>
mpcr reviewer update --status IN_PROGRESS --phase <PHASE>
mpcr reviewer note --note-type question|blocker_preview|domain_observation --content "..."
mpcr reviewer finalize --verdict <V> [--blocker N --major N --minor N --nit N] [--report-file path] [--copy-report-input] [--no-auto-close-children]
mpcr reviewer complete-child --reviewer-id <ID8> --session-id <ID8> --verdict <V> [--blocker N --major N --minor N --nit N] [--report-file path] [--proof-note TEXT]
mpcr session reports open|closed|in-progress [--include-report-contents]
```
