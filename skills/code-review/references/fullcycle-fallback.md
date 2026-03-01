# Full-Cycle Fallback

Primary source: `mpcr protocol fullcycle`.

If the CLI is unavailable, use the section below.

## Full-Cycle Orchestration (`FULLCYCLE`)

Full-cycle runs Reviewer then Applicator with recursive Convergence control. You SHALL follow this protocol EXACTLY.

## Preconditions
- You are the orchestrator. You do NOT read code, write patches, or produce findings.
- All work is done by subagents. You coordinate, validate, and loop.
- You SHALL run `mpcr protocol scope-mapping` and `mpcr protocol convergence-planning` before launching cycle 1 workers.

## Phase 1: Initial Review
1. Run the complete Reviewer workflow (see main orchestrator protocol above).
2. Collect the merged report and ship-readiness verdict.
3. IF ship-readiness verdict is **SHIP** (zero BLOCKER/MAJOR findings) -> STOP. Present report to user. You are done.
4. OTHERWISE -> proceed to Phase 2.

## Phase 2: Application
1. Run the Applicator workflow on the findings from Phase 1.
2. BEFORE dispatching applicator workers, dispatch `scope-mapper-applicator` and pass the Scope Map packet from cycle start.
3. Dispatch `convergence-planner` with prior-cycle summaries to propose focus boundaries for this cycle.
4. You SHALL dispatch applicator-worker subagents for APPLIED findings (subject to concurrency cap of 8).
5. Each applicator-worker SHALL spawn its own explorer subagents for evidence challenge verification.
6. Collect all Application Reports. Record dispositions via `mpcr applicator note --session-dir <DIR> ...`.
7. Set status: `mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status APPLIED`.

## Phase 3: Scoped Re-Review
1. Identify the delta: files modified by applicator-workers in Phase 2.
2. Run a NEW reviewer workflow targeting ONLY the delta files.
   - You SHALL use fresh subagents (not reuse prior-cycle workers).
   - You SHALL NOT re-examine code that was reviewed in earlier cycles and not modified.
   - Spawn domain specialists relevant to the delta only (not all seed domains), but you SHALL always include `staleness-auditor`.
   - Dispatch `scope-creep-reviewer` for explicit scope containment challenge.
   - The ship-readiness-assessor runs last, as in Phase 1.
3. Collect the re-review report and ship-readiness verdict.

## Phase 4: Convergence Check
1. Compute net-new actionable findings:
   - BLOCKER and MAJOR findings from re-review
   - Staleness-domain findings that indicate mismatched shipped behavior or operator guidance drift
2. IF net-new actionable findings == 0 -> STOP. Present final report to user.
3. IF net-new actionable findings > 0:
   - Run Phase 2 again on net-new findings only.
   - Run Phase 3 and Phase 4 again on resulting delta.
   - Proceed to Phase 4 again.

## Recursive constraints
- No hard numeric cycle cap is imposed by protocol.
- You SHALL recurse until a fixed point is reached (zero net-new actionable findings).
- Each cycle SHALL use fresh subagents to prevent convergent laziness.
- The orchestrator SHALL keep a cycle ledger with unique finding fingerprints (`severity + anchor + normalized claim`).
- You SHALL deduplicate by fingerprint across cycles before deciding net-new counts.
- You SHALL present the user a cycle summary at each stop point:
  - Cycle N complete. Applied: N findings. Declined: N. Deferred: N. Net-new from re-review: N. Net-new staleness: N.
  - Ship-readiness verdict: SHIP / SHIP_WITH_FIXES / DO_NOT_SHIP.
- WHEN recursion does not converge due to repeated malformed worker outputs, you SHALL mark unresolved items as Residual Risk and stop only when no new valid findings are produced.

## Artifact cleanup
AFTER the workflow completes (finalize succeeds or full-cycle converges):
- You SHALL delete `.local/tmp/` if it exists: `find .local/tmp -delete 2>/dev/null || true`
- You SHALL NOT leave dispatch prompts, report templates, packet files, or any other scratch artifacts in the worktree.
- You SHALL verify no files were written to the repo root (outside `.local/`) by the review process.

## Worker dispatch prompt updates
WHEN dispatching workers, you SHALL include ALL phase transitions in the task steps, not only INGESTION:
1. `mpcr reviewer update --session-dir <DIR> ... --phase INGESTION` - after reading assigned files
2. `mpcr reviewer update --session-dir <DIR> ... --phase DOMAIN_COVERAGE` - after scoping decisions
3. `mpcr reviewer update --session-dir <DIR> ... --phase THEOREM_GENERATION` - after generating theorems
4. `mpcr reviewer update --session-dir <DIR> ... --phase ADVERSARIAL_PROOFS` - after attempting disproofs
5. `mpcr reviewer update --session-dir <DIR> ... --phase SYNTHESIS` - after synthesizing findings
6. `mpcr reviewer update --session-dir <DIR> ... --phase REPORT_WRITING` - while producing the Proof Packet
7. `mpcr reviewer complete-child --session-dir <DIR> ... --verdict <V>` - self-completion (final step)

WHEN dispatching supplemental specialists, use the matching phase:
- complexity-analyst: `--phase COMPLEXITY_ANALYSIS`
- overengineering-guard: `--phase OVERENGINEERING_GUARD`
- ship-readiness-assessor: `--phase SHIP_READINESS`

## Worker dedup hints
WHEN multiple domain reviewers share files, you SHALL add an overlap note to each dispatch prompt:
```
## Overlap note
These files are also assigned to: [list other domain names].
Focus ONLY on your domain perspective. Do NOT duplicate findings from other domains.
```

## Error recovery
WHEN a worker returns malformed output (missing Proof Packet sections, no Domain Ledger, garbled):
1. Re-dispatch the worker with feedback: "Previous output was malformed. Missing: [sections]. Resubmit."
2. IF retry also fails, record the gap as Residual Risk. Do NOT fabricate findings.
3. WHEN a worker crashes or times out, mark child as ERROR and note the gap.
