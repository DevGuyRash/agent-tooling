# Full-Cycle Fallback

Primary source: `mpcr protocol fullcycle`.

If the CLI is unavailable, use the section below.

## Full-Cycle Orchestration (`FULLCYCLE`)

Full-cycle runs Reviewer then Applicator with recursive Convergence control. You SHALL follow this protocol EXACTLY.

## Preconditions
- You are the orchestrator. You do NOT read code, write patches, or produce findings.
- All work is done by subagents. You coordinate, validate, and loop.
- You SHALL run `mpcr protocol scope-mapping` and `mpcr protocol convergence-planning` before launching cycle 1 workers.
- For deterministic orchestration state, you SHALL treat `mpcr fullcycle plan`, `mpcr fullcycle loop-plan`, `mpcr fullcycle checkpoint`, and `mpcr fullcycle state` as the execution bridge between protocol guidance and session state.
- WHEN user intent explicitly requests a fresh start, you SHALL run `mpcr reviewer register` with `--clear-session-day` (single date) or `--clear-all-session-days` (all date directories) before cycle 1 registration. IF user intent does not request cleanup, you SHALL NOT pass either cleanup flag.

## Phase 1: Initial Review
1. Run the complete Reviewer workflow (see main orchestrator protocol above).
2. Collect the merged report and ship-readiness verdict.
3. IF the merged report has zero BLOCKER, zero MAJOR, zero behavior-facing staleness findings, and zero remaining MINOR/NIT findings -> STOP. Present report to user. You are done.
4. IF only MINOR/NIT findings remain -> proceed to Phase 5.
5. OTHERWISE -> proceed to Phase 2.

## Phase 2: High-Severity Application
1. Run the Applicator workflow on the findings from Phase 1.
2. BEFORE dispatching applicator workers, dispatch `scope-mapper-applicator` and pass the Scope Map packet from cycle start.
3. Dispatch `convergence-planner` with prior-cycle summaries to propose focus boundaries for this cycle.
4. You SHALL dispatch applicator-worker subagents only for APPLIED findings that are required now (BLOCKER/MAJOR or behavior-facing staleness that affects shipped behavior or operator guidance) (with dynamic worker budget (baseline 4; probe 6 and 8 cautiously when cycle health is stable)).
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
1. Compute the reopen bar:
   - net-new BLOCKER and MAJOR findings from re-review
   - Staleness-domain findings that indicate mismatched shipped behavior or operator guidance drift
   - Parent-report machine blocks SHALL encode `reopen_eligible = true` only for those behavior-facing staleness findings/residual risks; follow-up-only stale polish SHALL remain `false`
   - IF resuming parent reports that predate `reopen_eligible`, the planner SHALL stop and mark the session fresh-start-required unless an explicit migration path is documented
2. IF the reopen bar is non-zero:
   - Run Phase 2 again on those required-now findings only.
   - Run Phase 3 and Phase 4 again on the resulting delta.
   - Proceed to Phase 4 again.
3. IF the reopen bar is zero and remaining findings are only MINOR/NIT -> proceed to Phase 5.
4. IF the reopen bar is zero and no remaining findings exist -> STOP. Present final report to user.

## Phase 5: Terminal Minor Cleanup
1. Batch the remaining verified MINOR/NIT findings into one terminal cleanup pass.
2. Applicator workers SHALL NOT self-expand that pass into adjacent cleanup beyond assigned findings.
3. After application, record which MINOR/NIT findings were applied, deferred, declined, or already addressed.
4. Proceed to Phase 6.

## Phase 6: Final Minor Check
1. Run exactly one final delta-only reviewer workflow against the files modified during Phase 5.
2. IF the final check finds any BLOCKER, MAJOR, or behavior-facing staleness -> reopen Phase 2 on those findings only.
3. IF the final check finds only MINOR/NIT (or no findings) -> STOP. Present the report and carry any remaining MINOR/NIT as follow-up or residual polish.

## Recursive constraints
- No hard numeric cycle cap is imposed while BLOCKER/MAJOR or behavior-facing staleness findings continue to appear.
- You SHALL recurse until the high-severity reopen bar reaches a fixed point.
- Terminal MINOR/NIT cleanup is single-shot: one cleanup pass plus one final delta-only check.
- Each cycle SHALL use fresh subagents to prevent convergent laziness.
- The orchestrator SHALL keep a cycle ledger with unique finding fingerprints (`severity + anchor + normalized claim`).
- You SHALL deduplicate by fingerprint across cycles before deciding whether the reopen bar is non-zero.
- You SHALL present the user a cycle summary at each stop point:
  - Cycle N complete. Applied: N findings. Declined: N. Deferred: N. Net-new from re-review: N. Net-new staleness: N.
  - Ship-readiness verdict: SHIP / SHIP_WITH_FIXES / DO_NOT_SHIP.
- WHEN recursion does not converge due to repeated malformed worker outputs, you SHALL mark unresolved items as Residual Risk and stop once the reopen bar is clear and no new valid high-severity findings are produced.

## Artifact cleanup
AFTER the workflow completes (finalize succeeds or full-cycle converges):
- You SHALL delete `.local/tmp/` if it exists:
  - POSIX: `rm -rf .local/tmp/`
  - PowerShell: `Remove-Item -Force -Recurse .local/tmp/ -ErrorAction SilentlyContinue`
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
