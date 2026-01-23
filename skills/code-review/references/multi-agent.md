# Multi-agent orchestration protocol

**Status:** Canonical baseline  
**Role:** Orchestrator + Subagents (internal helpers)  
**Goal:** Increase depth and throughput via parallel reasoning without sacrificing determinism, auditability, or mpcr hygiene.  
**Change control:** Production-stable. Additive clarifications only; breaking changes require an explicit version bump.

---

## 0) Quickstart (mandatory when subagents are available)

WHEN subagents / parallel workers are available THEN the orchestrator SHALL:

- delegate early (before deep sequential ingestion)
- use disjoint responsibilities with explicit scopes (files/anchors/domains)
- keep the orchestrator as the single writer of:
  - the final deliverable (UACRP report or dispositions)
  - repository edits / commits
  - `mpcr` mutations for the orchestrator entry and applicator state, EXCEPT for Child Reviewers (optional)
- require each subagent to follow the workflow-specific contract file:
  - Reviewer → `<skills-file-root>/references/perform/subagent-contract.md` (Proof Packet)
  - Applicator → `<skills-file-root>/references/apply/subagent-contract.md` (Disposition Packet)
- stop delegating only when the saturation stop condition is met (no new failure modes / evidence / mitigations).

Default initial roster (start here unless the user specifies otherwise):

1) **Scope Mapper:** anchored change inventory + trust boundaries + draft depth targets.  
2) **Red Team:** concrete disproof attempts against the riskiest theorems / trust boundaries.  
3) **Systems Auditor:** concurrency/perf/operability scan + verification plan.

IF you are performing the **Applicator** workflow THEN you SHOULD prefer the Applicator delegation plan:

- **Report Extractor**, **Anchor Verifier**, **Patch Designer** (see `<skills-file-root>/references/apply-overview.md`).

IF UACRP escalation triggers apply THEN you SHOULD add redundancy:

- a second independent **Depth Diver** assigned to the single highest-risk depth target.

There SHALL exist a delegation record for auditability:

- IF `mpcr` is in use THEN the orchestrator SHALL record the delegation as a note:
  - Reviewer workflow → `note-type: handoff` (role: reviewer)
  - Applicator workflow → `note-type: handoff` (role: applicator)
- OTHERWISE the roster and scopes SHALL appear in the final deliverable.

---

## I) Core model

### Roles

- **Orchestrator (you):** The single agent that SHALL be responsible for:
  - producing the final deliverable (UACRP report or dispositions)
  - running `mpcr` mutations for the orchestrator’s own reviewer entry and for applicator state (status/notes)
  - making any repository edits (working tree, commits)

- **Subagents:** Parallel analysts that produce packets for the orchestrator to merge.
  - Default posture: **read-only** (Subagents SHALL be read-only unless explicitly granted write access)
  - Subagents are NOT “reviewers” and are NOT “applicators” for mpcr purposes.
- **Child Reviewers (optional; mpcr-integrated):** Parallel agents that act as full mpcr reviewers and produce their own UACRP reports.
  - The orchestrator still synthesizes the overall outcome, but each Child Reviewer SHALL own its own mpcr reviewer entry (status/notes/report).
  - Use ONLY when you need independent report artifacts recorded via `mpcr`.
  - Child Reviewers SHALL follow `<skills-file-root>/references/perform/child-reviewer-contract.md`.

### `mpcr` CLI location (this skill)

Within this skill, `mpcr` refers to `<skills-file-root>/scripts/mpcr`.

---

## II) Capability detection and fallback

Work SHALL run in **MULTI_AGENT** mode when subagents are available; otherwise it SHALL run in **SINGLE_AGENT** mode using the same decomposition.
The orchestrator SHALL determine availability at the start so the correct mode is selected.

In both modes, the orchestrator SHALL remain the single writer of repository edits and the overall final deliverable.
Child Reviewers (if used) SHALL write artifacts only for their own mpcr reviewer entry (status/notes/report).

### Timing (mandatory; early delegation)

IF subagents / parallel workers are available THEN multi-agent execution SHALL begin early.
You SHALL NOT defer delegation until after you have already performed deep sequential ingestion of the entire codebase/diff/reports.

There SHALL exist:

- a short sequential **Plan/Outline** that defines the decomposition (objectives + disjoint scopes), AND
- parallel delegated work for the remaining depth/coverage effort.

You SHALL ask the user how much parallelism they want (no fixed cap). If the user gives a concurrency budget, you SHALL respect it (use waves if needed); otherwise you SHALL continue delegating until the saturation stop condition defined in Section IV is met.

---

## III) Determinism and write-ownership rules

### Orchestrator write ownership (default)

The orchestrator SHALL be the only actor that:

- edits repository files
- commits / rebases / pushes
- runs `mpcr reviewer register/update/note/finalize` for the orchestrator’s own reviewer entry
- runs `mpcr applicator set-status` or `mpcr applicator note`

### Child Reviewer write ownership (optional; mpcr-integrated)

IF the orchestrator delegates a child agent as a **Child Reviewer** THEN that child reviewer SHALL:

- remain read-only w.r.t the repo (patches/suggestions only)
- use `mpcr` ONLY for `mpcr reviewer register/update/note/finalize` for its own reviewer entry
- follow `<skills-file-root>/references/perform/child-reviewer-contract.md`

### Subagent restrictions (default)

Subagents SHALL NOT:

- run `mpcr` commands
- change `initiator_status`
- edit repository files
- write to `_session.json` directly

Subagents MAY:

- read code and diffs
- run read-only inspection commands (e.g., `rg`, `git show`, `cat`)
- propose fixes as text diffs / patch suggestions
- propose verification commands and tests

IF the orchestrator explicitly grants “write access” to a subagent THEN the orchestrator SHALL:

- scope it to specific files/anchors
- state the merge strategy (patch-only; no direct edits preferred)
- state how conflicts will be resolved

---

## IV) Orchestration outcomes (multi-agent)

This section is outcome-focused: it defines WHAT you need to achieve and WHY.
It intentionally avoids prescribing a single fixed decomposition or a fixed number of agents.

### A) Reviewer outcomes (dynamic; no fixed cap)

WHEN performing a review AND subagents are available THEN the orchestrator SHALL obtain a **dynamic** set of Proof Packets (and/or Child Reviewer UACRP reports) with **disjoint responsibilities**.
The orchestrator SHALL NOT impose an arbitrary upper bound; it SHALL continue delegating work (in waves if needed) until:

- Universal Domain coverage is complete, AND
- additional independent analysis stops producing new failure modes / evidence / mitigations (saturation stop condition).

Required outcomes (why: determinism + depth + auditability):

- **Scope model:** there SHALL exist an anchored change inventory, trust boundary map, contract surface list, and explicit depth targets.
- **Must‑prove theorems:** there SHALL exist anchored must‑prove theorems for every in-scope Universal Domain and for each depth target.
- **Concrete disproof attempts:** there SHALL exist concrete counterexample attempts for those theorems (even when concluding “no issue found”).
- **Verification plan:** there SHALL exist a verification plan that would fail if key risks still exist (tests/commands/artifacts).
- **Residual risk:** there SHALL exist explicit Assumed/Unknown claims with why-they-matter + how-to-verify.
- **Saturation rationale:** there SHALL exist a recorded reason you stopped delegating (why additional agents would not add new failure modes / evidence).

Non-normative examples (do not treat as an exhaustive or mandatory role list):

- **Scope Mapper:** Produces the scope model (inventory + trust boundaries + depth targets) so downstream proofs are focused.
- **Red Team:** Tries to break correctness/security claims via counterexamples, attack paths, and failure scenarios.
- **Systems Auditor:** Assesses concurrency/perf/operability/dependencies/technical debt and identifies verification gaps.

Subagents and Child Reviewers SHALL tailor their proof effort to the specific change; they SHALL NOT default to a fixed canned role list when the change demands a different decomposition.

IF you need independent report artifacts saved via mpcr THEN you MAY delegate one or more agents as **Child Reviewers** instead of Subagents (see Section III).

### B) Applicator outcomes (provisional; stable baseline)

WHEN applying review feedback AND multiple review reports exist THEN the orchestrator SHALL use a **dynamic** amount of subagent help when available.
The orchestrator SHALL NOT impose an arbitrary upper bound; it SHALL process reports in waves if the runtime cannot execute them all concurrently.

Required outcomes (why: correctness + traceability):

- **Report ingestion:** each completed review report SHALL be read and its claims SHALL be verified against the current code at the cited anchors.
- **Disposition coverage:** each distinct failure mode SHALL receive a disposition decision (apply/decline/defer) with rationale and verification implications.
- **Deterministic state:** progress and dispositions SHALL be recorded via `mpcr` (applicator notes/status) instead of ad-hoc state.

IF outputs appear shallow OR the change is high-risk THEN the orchestrator SHALL increase depth until the saturation stop condition is met (including by using the depth-increase techniques in Section VIII when useful).

---

## V) Workflow-specific contract files (progressive disclosure)

Subagents SHALL follow the contract file provided by the orchestrator:

- Reviewer → `<skills-file-root>/references/perform/subagent-contract.md` (Proof Packet)
- Applicator → `<skills-file-root>/references/apply/subagent-contract.md` (Disposition Packet)

Child Reviewers (optional; mpcr-integrated) SHALL follow:

- `<skills-file-root>/references/perform/child-reviewer-contract.md`

---

## VI) Dispatch content (outcome-focused)

WHEN the orchestrator launches a subagent THEN the orchestrator SHALL provide:

- assignment objective (WHAT/WHY)
- explicit scope (FILES / ANCHORS)
- domains / risk lens (optional but preferred)
- the relevant contract file path (see Section V)

IF the assignee is a Child Reviewer THEN the orchestrator SHALL also provide the mpcr session context required by the child reviewer contract.

Deliverable:

- You SHALL return exactly one artifact:
  - Subagent → one workflow-specific packet (per the contract file in Section V)
  - Child Reviewer → one UACRP report (template in `references/perform/uacrp.md`)

Output format requirement (Subagents):

- Reviewer subagent response SHALL begin with: `## Proof Packet: <NAME>`
- Applicator subagent response SHALL begin with: `## Disposition Packet: <NAME>`

---

## VII) SINGLE_AGENT fallback (no subagents)

IF subagents are not available THEN the orchestrator SHALL:

- achieve the same required outcomes from Section IV sequentially
- produce the equivalent packet content internally
- then synthesize into the final report/dispositions
---
## VIII) Depth increase (triggered; outcome-driven)

WHEN the change is high-risk OR outputs appear shallow THEN the orchestrator SHALL increase depth until the saturation stop condition is met.
This section lists non-normative techniques that can be used to achieve that outcome.

### 1) Counterexample-first reporting

- Subagents and Child Reviewers SHOULD begin each theorem with the concrete disproof attempt and only then state outcome (why: auditability and reduced hand-waving).

### 2) Redundant review on one depth target

IF the change is high-risk THEN there SHALL exist at least two independent analyses of the single highest-risk depth target.
- The orchestrator SHALL surface any disagreement explicitly (do not silently average conclusions).

### 3) Proof-carrying findings

For each BLOCKER/MAJOR finding (Proof Packet or Child Reviewer report):

- there SHALL exist a minimal reproducer (input payload, call sequence, or state-machine trace), AND
- there SHALL exist an explicit “How to verify” plan that would fail if the bug still exists.

### 4) Noise budget (anti-bloat)

- Non-normative guidance: Subagents SHOULD aim for concise findings (commonly ≤ 5) by default.
- IF additional unique failure modes keep appearing THEN subagents SHALL continue until saturation, then stop.

### 5) Theorem bounty board (counterexample dispatch)

WHEN outputs appear shallow OR the change is high-risk THEN the orchestrator SHOULD:

- produce a short list (≤ 15) of the highest-risk must-prove theorems, each with:
  - a stable id (T1, T2, …)
  - an anchor (path:line + symbol/snippet)
  - the claim to be disproved
- delegate subagents to attempt concrete disproof attempts for assigned theorem ids.

Subagents SHOULD preserve theorem ids in their packets so synthesis is traceable.

### 6) Packet-to-report mapping (anti-synthesis overhead)

Subagents SHOULD declare which final sections their packet informs (UACRP sections for Reviewer; finding dispositions for Applicator).
The orchestrator SHOULD use those mappings to place evidence without re-tracing every packet end-to-end.

### 7) Depth playbook (progressive disclosure)

IF you are performing the Reviewer workflow AND you cannot produce an anchored adversarial trace THEN you SHOULD read:
`<skills-file-root>/references/perform/depth-playbook.md`
and redelegate targeted depth work.
