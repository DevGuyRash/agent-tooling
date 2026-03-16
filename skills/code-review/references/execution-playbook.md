# Execution Playbook

Concrete, numbered execution procedures for all three code-review modes.
SKILL.md routes here after `mpcr route`. Policy checklists live in the
`*-fallback.md` references and `mpcr protocol` output — this file covers
the step-by-step workflow only.

---

## Role detection

IF your prompt includes dispatch markers (assigned scope, `reviewer_id`
bindings, `MPCR_DISPATCH_ROLE`) THEN you SHALL follow the dispatch prompt
only; you SHALL NOT run orchestrator commands (`register`, `spawn-routed`,
`finalize`).

ELSE you SHALL follow the Orchestrator workflow for your mode below.

---

## Execution model

WHEN the diff is ≤ 500 lines AND the user did not request multi-agent THEN
you SHALL spawn exactly one worker subagent.

WHEN the diff is > 500 lines OR the user requests multi-agent THEN you
SHALL spawn specialist workers in parallel.

You SHALL run at most 8 parallel subagents. WHEN 8 are active THEN you
SHALL wait for one to complete before launching another.

You SHALL NOT read code files directly as the orchestrator. You SHALL
dispatch all first-hand exploration to routed workers.

You SHALL reuse the exact `persisted.session_dir` and the same `target-ref`
string for every command in a session. You SHALL NOT point `--session-dir`
at scratch or ad hoc directories.

---

## Reviewer workflow

### Step 1 — Collect scope inputs

Gather changed files, public interfaces, and behavior-facing artifacts from
the user request, PR context, or `git diff`.

IF `changed_files` is empty THEN you SHALL abort with error; you SHALL NOT
proceed with an empty surface map.

### Step 2 — Route

You SHALL run:

```
mpcr route --persist --mode reviewer --target-ref <REF> \
  --execution-capability parallel_subagents \
  --max-worker-count <n> \
  --orchestrator-read-budget-lines <n> \
  --orchestrator-read-budget-snippets <n> \
  [--changed-file <path>]... \
  [--public-interface <path>]... \
  [--behavior-facing-artifact <path>]...
```

Captures: `persisted.session_dir`, `route_decision.worker_plan`.

For a fresh isolated session, you SHALL prefer an unused canonical date
leaf via `--repo-root <path> --date <yyyy-mm-dd>`. One canonical date leaf
holds one session. IF that leaf already belongs to a different `target-ref`
THEN you SHALL pick another date or run
`mpcr session cleanup --session-dir <path>` before rerouting.

### Step 3 — Register root anchor

You SHALL run:

```
mpcr reviewer register --target-ref <same-REF> \
  --session-dir <persisted.session_dir>
```

Captures: `root-reviewer-id` (the orchestration anchor).

### Step 4 — Spawn workers

You SHALL run:

```
mpcr reviewer spawn-routed --parent-id <root-reviewer-id> \
  --session-dir <persisted.session_dir>
```

Captures: list of `{ reviewer_id, role, agent_dir }`.

IF `spawn-routed` returns zero workers THEN you SHALL abort; you SHALL NOT
proceed without materialized workers.

WHEN `spawn-routed` materializes more workers than `max_worker_count` THEN
you SHALL batch workers into parallel rounds of at most `max_worker_count`.
Workers whose domain has no plausible findings for the changed files
(e.g. `dependency` when only stdlib is imported, `scope-creep` on an
initial commit) SHALL be closed with a categorical `NO_FINDINGS` or
`LOW_SIGNAL` outcome via `complete-child` rather than launched as
subagents.

### Step 5 — Load dispatch prompts

For EACH spawned worker, you SHALL run:

```
mpcr protocol dispatch --role <role> --session-dir <persisted.session_dir> \
  --reviewer-id <worker-reviewer-id> --view checklist
```

You SHALL use the spawned worker's `reviewer_id` for session-bound prompts,
not the root anchor.

### Step 6 — Launch workers as parallel subagents

You SHALL use the Agent tool to launch each worker as a parallel
subagent. You SHALL NOT absorb worker scope into the orchestrator.

You SHALL pass each dispatch prompt as the worker's sole instructions.
You SHALL include session bindings (`reviewer_id`, `session_dir`,
`target-ref`) in each worker prompt.

You SHALL include the canonical `child_findings` schema reference in
each worker prompt so workers can produce valid artifacts:

```
Refer to <skills-file-root>/references/examples/reviewer-child-findings.toml
for the required child_findings schema. Key constraints:
- artifact_id: exactly 12 lowercase hex characters
- producer_kind: must match your worker_kind
- Required top-level fields: schema_version, artifact_kind, artifact_id,
  session_id, target_ref, producer_kind, policy_version, created_at,
  confidence_label, confidence_score, worker_kind, role_id, module_ids,
  claimed_scope, delegated_scope, research_refs, route_revision_refs,
  loaded_policy_refs, findings
- Each finding requires: finding_id, module_id, surface_ids, severity
  (lowercase), title, claim, scenario, evidence, recommendation,
  verification, anchors, fingerprint, reopen_eligible, confidence_label,
  confidence_score, evidence_strength, false_positive_risk, actionable,
  duplicate_suspect
- Each defended_checks entry requires: check_id, module_id, surface_ids,
  method, claim, attempted_counterexample, evidence, anchors,
  confidence_label, confidence_score
```

Each worker SHALL:

1. Read the assigned code files and produce findings.
2. Record at least one defended non-finding: an attack surface or
   invariant the worker explicitly checked and confirmed clean, with
   the reasoning that rules it out (e.g. "Checked `DB_PATH` for
   caller-controllability: module-level constant, not user-supplied.
   No path traversal risk."). Workers SHALL NOT leave the
   `defended_checks` array empty when findings exist — the absence
   of non-findings signals incomplete investigation, not a clean
   codebase.
3. Write a full authored `report.md` (≥ 200 words with `file:line`
   anchors) to its `agent_dir` BEFORE running `complete-child`.
   `complete-child` may overwrite the scaffold report, but the worker
   SHALL NOT rely on auto-rendering alone. The report SHALL be a
   coherent narrative, not just a bullet list — explain WHY each
   issue is dangerous, trace the concrete exploit or failure path,
   and connect related findings.
4. Write `child_findings.toml` to `<session_dir>/artifacts/<reviewer_id>/`.
5. Run:

```
mpcr reviewer complete-child --reviewer-id <worker-id> \
  --session-dir <persisted.session_dir> \
  --artifact-file <child_findings.toml>
```

Note: `producer_kind` in the TOML SHALL match the worker's registered
`worker_kind` (e.g. `language-detector` for language-detector workers,
`domain-reviewer` for domain workers). A mismatch causes validation
failure.

### Step 7 — Collect results

You SHALL wait for all workers to complete before proceeding to synthesis.

### Step 8 — 3-voter legitimacy gate

Each candidate finding SHALL be validated by 3 independent voters
before it enters the parent review. Each voter receives a minimal
packet containing ONLY:

- `finding_id`, `fingerprint`
- claim and scenario
- anchors (`path:line`)
- call-chain summary
- ruled-out neutralizers
- minimal surrounding refs (≤ 30 lines of source context per anchor)

Voters SHALL validate only — you SHALL NOT let voters edit code, write
artifacts, or broaden scope.

WHEN the finding count is ≤ 8 THEN you SHALL spawn 3 voter subagents
per finding with isolated packets (voters SHALL NOT see other findings).

WHEN the finding count exceeds 8 THEN you SHALL batch findings by
severity tier to control subagent cost:

- BLOCKER findings: 3 dedicated voters per finding (isolated packets)
- MAJOR findings: batch into groups of ≤ 4 findings per voter set
- MINOR findings: batch all into one voter set of 3

Each voter votes `legitimate` or `false-positive` per finding with a
one-sentence rationale.

IF 2-of-3 vote "legitimate" THEN the finding proceeds.

ELSE you SHALL record the finding as false-positive:

```
mpcr reviewer note --reviewer-id <root-reviewer-id> \
  --content "<compact false-positive rationale>"
```

### Step 9 — Dispatch final-synthesizer

You SHALL run:

```
mpcr protocol dispatch --role final-synthesis \
  --session-dir <persisted.session_dir> \
  --reviewer-id <root-reviewer-id> --view checklist
```

You SHALL include the canonical `parent_review` schema reference in the
synthesizer prompt so it can produce valid artifacts:

```
Refer to <skills-file-root>/references/examples/reviewer-parent-review.toml
for the required parent_review schema. Key constraints beyond child_findings:
- source_artifact_ids: list all contributing child artifact IDs
- severity_rationale: optional string on [[required_now]] findings whose
  severity was changed from the child worker's original assessment
- defended_summary: aggregate defended_checks from child workers
- ship_readiness: verdict, axes, blocking_items, required_now_count,
  follow_up_count
- coverage_summary: changed_files, surfaces_covered, modules_loaded,
  limitations
```

The synthesizer SHALL:

- Concatenate descendant reports in stable order, preserve machine
  counts from artifacts, and surface only legitimacy-gated findings.
- Deduplicate cross-domain overlaps. WHEN the same code location
  appears in multiple domain findings THEN keep the primary domain's
  version and record which source artifact IDs were merged.
- WHEN child workers assign different severities to the same
  underlying defect THEN the synthesizer SHALL record a severity
  rationale explaining the canonical choice.
- Produce a **compositional risk analysis** section that traces
  cross-domain attack chains and compound failure modes. Findings
  SHALL NOT be listed in isolation when they interact — the
  synthesizer SHALL explain how findings combine to amplify risk
  (e.g. "SQL injection + hardcoded key + no rate limiting form a
  compound authentication bypass chain").
- Aggregate `defended_checks` from child workers into a
  `defended_summary` in the parent review.
- Produce a specific push-or-stop recommendation that names the
  blocking findings by ID and states the concrete ship decision.
  The recommendation SHALL NOT be generic boilerplate.

### Step 10 — Validate

You SHALL run:

```
mpcr validate --artifact-file <parent_review.toml> \
  --kind parent-review --layer hard
```

Hard validation is BLOCKING. IF validation fails THEN you SHALL
re-dispatch the failing worker (max 1 retry). IF retry also fails THEN
you SHALL record the gap as Residual Risk; you SHALL NOT fabricate
findings.

### Step 11 — Finalize

You SHALL run:

```
mpcr reviewer finalize --session-dir <persisted.session_dir>
```

---

## Quality gate

Every reviewer-mode outcome SHALL pass these criteria before finalization:

| Criterion | Pass | Fail |
|---|---|---|
| Scope coverage | Worker covered assigned files | Files skipped without justification |
| Finding specificity | Concrete `file:line` anchors, falsifiable claims | Generic "code looks fine" |
| Evidence grounding | Findings cite actual existing code | Fabricated references |
| Severity evidence | BLOCKER/MAJOR have trigger path + impact | Severity asserted without evidence |
| Call-chain challenge | Introducing path AND downstream effect traced | Surface-level observation only |
| Counterevidence | Later guards/normalization/rollback ruled out | Neutralizing code ignored |
| Defended non-findings | ≥ 1 explicit "checked and found clean" per worker | Empty `defended_checks` when findings exist |
| Compositional analysis | Synthesis traces cross-domain attack chains | Findings listed without connection |
| Severity rationale | Cross-worker severity discrepancies explained | Silent downgrade/upgrade without justification |
| Narrative coherence | Report reads as a review, not a bullet dump | Disconnected finding list with no reasoning |

---

## Applicator workflow

### Step 1 — Ingest findings

You SHALL read the finalized `parent_review` artifact to obtain the finding
roster and their dispositions.

### Step 2 — Route for applicator

You SHALL run:

```
mpcr route --persist --mode applicator --target-ref <REF> \
  --execution-capability parallel_subagents \
  --session-dir <persisted.session_dir> \
  [--changed-file <path>]...
```

### Step 3 — 3-voter legitimacy gate BEFORE editing code

For EACH candidate finding, you SHALL run the same 3-voter gate described
in Reviewer Step 8.

You SHALL NOT edit code for any finding that has not cleared the vote.

WHEN a finding fails the vote THEN you SHALL decline it categorically in
`application_result` and record the reason:

```
mpcr applicator note --content "<compact false-positive rationale>"
```

### Step 4 — Evidence challenge

For EACH finding that cleared the vote, you SHALL challenge:

- Anchor quality — does the `path:line` still exist and match?
- Scenario realism — is the trigger path plausible?
- Severity proportionality — does evidence support the claimed severity?
- Hallucination check — does the referenced code actually exist?
- Duplication — is this finding already addressed or a duplicate?
- Downstream neutralization — do later guards already handle it?

IF challenge fails THEN you SHALL decline with a categorical reason.

### Step 5 — Spawn applicator workers per file cluster (max 8 parallel)

You SHALL dispatch workers grouped by file cluster. Each worker applies
accepted findings, records dispositions, and emits its portion of
`application_result`.

```
mpcr applicator set-status --finding-id <id> --status applied \
  --session-dir <persisted.session_dir>
```

### Step 6 — Finalize application result

You SHALL run:

```
mpcr validate --artifact-file <application_result.toml> \
  --kind application-result --layer hard
mpcr applicator finalize --artifact-file <application_result.toml>
```

### Step 7 — Verify exactly the finding IDs in `verification_needed`

You SHALL verify every finding ID listed in
`application_result.verification_needed`. You SHALL NOT skip verification.

Partial or failed verification keeps the applicator blocked.

```
mpcr applicator verify --artifact-file <verification_result.toml>
```

### Step 8 — Set status

You SHALL run:

```
mpcr validate --artifact-file <verification_result.toml> \
  --kind verification-result --layer hard
```

---

## Full-cycle workflow

### Phase 1 — Review

You SHALL run the complete Reviewer Workflow (Steps 1–11 above).

IF the outcome is SHIP with zero BLOCKER/MAJOR findings THEN you SHALL
STOP. The review is complete.

### Phase 2 — Apply

You SHALL run the Applicator Workflow (Steps 1–8 above) on Phase 1
findings.

### Phase 3 — Scoped re-review

You SHALL run a fresh review on delta files only (files modified during
Phase 2). You SHALL spawn fresh subagents for this phase.

You SHALL NOT reuse Phase 1 workers. You SHALL NOT re-examine unchanged
files.

```
mpcr fullcycle plan --output <convergence_plan.toml>
mpcr fullcycle checkpoint --artifact-file <convergence_state.toml>
```

### Phase 4 — Convergence

IF zero net-new BLOCKER/MAJOR findings THEN you SHALL STOP.

IF cycle 1 AND net-new BLOCKER/MAJOR findings exist THEN you SHALL repeat
Phases 2–3 on net-new findings only.

WHEN cycle count reaches 2 THEN you SHALL hard-stop. Any remaining
unresolved findings SHALL be recorded as Residual Risk.

```
mpcr fullcycle state --session-dir <persisted.session_dir>
```

---

## Token discipline

You SHALL NOT paste raw diffs unless the user explicitly requests them.

Code excerpts: ≤ 12 lines, ≤ 3 excerpts total per orchestrator message.

Worker prompts: scope + acceptance criteria only. You SHALL NOT include
repo-wide context or conversation history in dispatch prompts.

---

## Quick reference — command examples

**Route (reviewer):**
```
mpcr route --persist --mode reviewer --target-ref HEAD \
  --execution-capability parallel_subagents --max-worker-count 6 \
  --orchestrator-read-budget-lines 200 --orchestrator-read-budget-snippets 5 \
  --changed-file src/auth.go --changed-file src/auth_test.go
```

**Register + spawn:**
```
mpcr reviewer register --target-ref HEAD --session-dir .local/reports/code_reviews/2026-03-15
mpcr reviewer spawn-routed --parent-id rv-001 --session-dir .local/reports/code_reviews/2026-03-15
```

**Dispatch:**
```
mpcr protocol dispatch --role domain-reviewer --session-dir .local/reports/code_reviews/2026-03-15 \
  --reviewer-id rv-002 --view checklist
```

**Worker finalize:**
```
mpcr reviewer complete-child --reviewer-id rv-002 \
  --session-dir .local/reports/code_reviews/2026-03-15 \
  --artifact-file .local/reports/code_reviews/2026-03-15/artifacts/rv-002/child_findings.toml
```

**Validate + finalize:**
```
mpcr validate --artifact-file .local/reports/code_reviews/2026-03-15/artifacts/parent_review.toml \
  --kind parent-review --layer hard
mpcr reviewer finalize --session-dir .local/reports/code_reviews/2026-03-15
```

**Applicator:**
```
mpcr route --persist --mode applicator --target-ref HEAD \
  --execution-capability parallel_subagents \
  --session-dir .local/reports/code_reviews/2026-03-15
mpcr applicator set-status --finding-id f-001 --status applied \
  --session-dir .local/reports/code_reviews/2026-03-15
mpcr applicator finalize --artifact-file <application_result.toml>
mpcr applicator verify --artifact-file <verification_result.toml>
```

**Full-cycle convergence:**
```
mpcr fullcycle plan --output convergence.toml
mpcr fullcycle checkpoint --artifact-file convergence_state.toml
mpcr fullcycle state --session-dir .local/reports/code_reviews/2026-03-15
```
