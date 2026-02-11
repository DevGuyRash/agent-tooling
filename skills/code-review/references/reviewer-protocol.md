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

`mpcr reviewer update --status IN_PROGRESS --phase INGESTION`

## Phase 2: Domain Coverage

You SHALL classify each Universal Domain for the change:

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

For each: In-scope (generate theorems), Out-of-scope (state why), or Unknown (note gap).
You SHALL mark at least 3 domains as In-scope for non-trivial changes.

`mpcr reviewer update --phase DOMAIN_COVERAGE`

## Phase 3: Theorem Generation

For each In-scope domain, you SHALL generate must-prove theorems:
- Concrete, falsifiable claims referencing specific code locations (file:line).
- You SHALL prioritize depth targets. At least 1 theorem per In-scope domain, 2-3 for depth targets.
- Theorems SHALL be disprovable — you SHALL NOT write truisms like "the code compiles."

`mpcr reviewer update --phase THEOREM_GENERATION`

## Phase 4: Adversarial Proofs

For each theorem, you SHALL attempt concrete disproof:
1. Construct a specific scenario/input that would violate the theorem.
2. Trace the code path. Record outcome:
   - DEFENDED: disproof failed; code handles it correctly.
   - FINDING: disproof succeeded; classify severity.

Severity: BLOCKER (must fix) > MAJOR (should fix) > MINOR (improvement) > NIT (style).

Saturation rule: you SHALL stop when 3 consecutive disproof attempts fail to find new issues.

WHEN tests exist that are relevant to your findings, you SHALL run them to validate your proofs.

`mpcr reviewer update --phase ADVERSARIAL_PROOFS`

## Phase 5: Synthesis

You SHALL compile findings. For each FINDING: severity, title, anchor (file:line), claim, disproof scenario, evidence, recommendation, verification plan.
For each DEFENDED theorem: anchor, disproof attempt, evidence, confidence.
You SHALL note residual risk: areas with insufficient coverage.

`mpcr reviewer update --phase SYNTHESIS`

## Phase 6: Report Writing

Select template scale based on change size:

### Compact (< 100 lines, single concern)
Summary + Findings + Defended Proofs + Residual Risk.

### Standard (medium changes)
Add: Domain Coverage Map, structured findings with full evidence.

### Full (large / high-risk)
All sections: Change Inventory, Acceptance Criteria, Domain Coverage Map, Theorems, Findings (full format), Defended Proofs table, Residual Risk, Verification Plan.

You SHALL finalize:
```
mpcr reviewer finalize --verdict APPROVE|REQUEST_CHANGES|BLOCK \
  --blocker N --major N --minor N --nit N --report-file report.md
```

## Non-negotiable rules

1. No ungrounded claims. Every finding SHALL have an evidence anchor (file:line or function).
2. Adversarial by default. You SHALL attempt to disprove every claim before accepting it.
3. Concrete scenarios only. "This could be a problem" is NOT a finding. You SHALL show the input/sequence.
4. Saturation stop. You SHALL NOT pad findings. Stop when you stop finding issues.
5. Scale to change. A typo fix does not need 11 domain sections.

## mpcr quick reference

```
mpcr reviewer register --target-ref <REF>
mpcr reviewer update --status IN_PROGRESS --phase <PHASE>
mpcr reviewer note --note-type question|blocker_preview|domain_observation --content "..."
mpcr reviewer finalize --verdict <V> [--blocker N --major N --minor N --nit N] [--report-file path]
mpcr session reports open|closed|in-progress [--include-report-contents]
```
