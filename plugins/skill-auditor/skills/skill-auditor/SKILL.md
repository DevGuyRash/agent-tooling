---
name: skill-auditor
description: Audit an existing skill or plugin for material evidence about target authority, executable behavior, host contracts, instruction design, and task value. Use for evidence-driven quality reviews, self-audits, release-risk investigation, or suspected packaging, routing, source, context, verification, or task-value drift. Delegates newly needed comparative evidence to Split Testing when available. Do not use to author a new skill or review ordinary source-code changes.
---

# Skill Auditor

Determine whether an existing skill or plugin earns its place, what materially weakens it, and what evidence supports retaining, changing, narrowing, or removing it. Serve the maintainer's decision, not the appearance of audit thoroughness. A clean result is valid.

Authoring a new skill belongs to `skill-creator`; ordinary source-code review is outside this skill’s scope. Do not modify the target unless the user asks. An audit does not authorize installation, registration, publication, cache mutation, or other user-level or external writes. Use a disposable environment or faithful simulation for observations that require mutation; otherwise leave the affected claim unverified.

## Proven mutation blind spot

Repeated held-out audits missed destructive behavior when a caller could bind a writable role and a protected role to the same runtime object. For any mechanism that can mutate external state while the target distinguishes what may and may not change, obtain raw before/after evidence establishing whether an allowed invocation can mutate protected state when caller-selected roles resolve to the same runtime object. This applies even when another blocker already decides release.

Prefer a fresh observer that sees the target-owned authority and requested evidence boundary before it sees the primary findings. If a fresh context is unavailable, perform the targeted observation in the primary audit and state that independence was unavailable; do not omit the observation or claim independence. Use only a disposable copy or faithful simulation of protected state. Remove this compensation when fresh dissimilar evaluations show reliable coverage without it.

## Evidence and authority

Start from the target's mission, declared entry points, adopted contracts, consequential mechanisms, tests, fixtures, and actual delivery boundary. A finding gains force from target or maker authority, an adopted consumer contract, or a demonstrated consequence. Familiar conventions, package shapes, validators, helpers, and auditor preferences are evidence only for what they actually observe. Do not turn them into target requirements without the governing link.

Ambient instructions govern the auditor where they apply; they do not automatically govern a copied, external, or independently maintained target. Preserve that boundary in delegated work and final judgment. Apply the [portable skill contract](references/open-standard.md) only when the target has adopted it, and the [repository overlay](references/repo-overlay.md) only where repository authority governs the target.

Inspect what could change the maintainer's decision. Declarations and passing examples do not prove their own claims. Prefer safe observations capable of falsifying consequential promises, and retain the raw result needed to reproduce a material finding. Derive those observations from this target's outcomes and boundaries rather than from a stock concern inventory.

When scripts, hooks, tools, generated commands, or other mechanisms can affect correctness, authority, safety, or delivery, use [executable evidence](references/executable-evidence.md). A broad audit of a consequential executable is not complete merely because source inspection or its normal example passed.

Use [instruction design](references/instruction-design.md) as the default design lens for AI instruction systems. Its governing block is adopted authority in this repository; elsewhere it supports evidence-backed design risks and recommendations unless separately adopted. Exact procedure is legitimate when required by a maker-set interface, named hazard, external contract, or observed model failure. Procedural form alone is not a defect.

Use [context and source evidence](references/context-and-source-evidence.md) when loading behavior, external authority, reference health, or version horizons could change a finding. Package size, file count, link presence, and prompt length are observations, not quality verdicts.

A task-value claim or any assertion that one alternative is better requires decision-linked evidence after deterministic inspection shows that the claim remains material. Use the [comparative handoff](references/comparative-handoff.md) for every newly needed comparison: invoke `$split-testing` with the claim, authority, existing evidence, constraints, and consequence in ordinary context, while Skill Auditor retains materiality, severity, repair, release, and reopening. When Split Testing is unavailable, assess fit existing evidence only; Skill Auditor does not recreate comparative method. If that evidence is insufficient, leave the claim unresolved, state its audit consequence, and preserve the evidence need in plain-language material state rather than inventing a request format. Explicit task trials do not prove implicit activation; use [trigger evidence](references/trigger-evals.md) when retrieval or coexistence is at issue.

For plugins, preserve per-skill task evidence and examine package behavior separately. Use [host contracts](references/host-contracts.md) for manifests, catalogs, installed copies, host ingestion, or publication; [plugin fit](references/plugin-fit.md) for sibling routing, composition, and package handoff; and [packaging fit](references/packaging-fit.md) for the delivery primitive. These routes are high-leverage decision aids, not a complete ontology or a required reading order.

## Independent observation

One context can repeatedly miss the same consequential property, especially after instructions make another concern salient. When a broad conclusion still depends on a materially distinct unresolved property, obtain an isolated observation of that property rather than another generic audit. Give the observer only the target, its governing authority, the property whose behavior must be established, and the evidence boundary to return. Do not provide prior findings, suspected implementation details, an expected answer, grading criteria, or this auditor skill. Require raw, reproducible observations and limitations rather than an audit verdict or repair proposal. If resolving the property requires comparing alternatives, use the comparative handoff instead of designing that comparison here.

Prefer the strongest available reasoning model for consequential discovery and reconciliation unless the user fixes another model or the question is deployment fidelity or cost. A fresh context, another agent, or agreement is not evidence by itself: verify the returned observation against the target, attribute its cost to the audit, and interpret it under the correct authority. Use as many distinct observers as the unresolved evidence requires and no more. If isolation or safe execution is unavailable, preserve the gap instead of simulating independence in the report.

## Judgment and completion

Report material defects by default and allow a clean result. Calibrate severity from reachable consequence, affected population, and the resulting repair or release decision—not from domain labels, hypothetical extremity, or finding count. A contradiction proves that represented states cannot all hold; it does not decide which meaning the maker intended. Preserve materially different repairs and the evidence or maker decision that would select among them.

Give the maintainer the supported direction, consequential evidence, smallest viable repair when one exists, and uncertainty or reopening conditions that could change the decision. Choose the clearest presentation for that audience; no fixed report sections or evidence labels are required.

For a broad audit, every target-owned consequential promise that could change the disposition must have falsifying evidence at its actual consumer boundary or remain visibly unverified. This is a target-derived coverage claim, not permission to enumerate generic edge cases or manufacture findings. Stop when further observations would not change the repair, release decision, or honest claim boundary.

Treat both diagnosis and repair as claims. When feasible, alter the earliest supported cause without changing unrelated conditions, recheck the failure boundary and consequential adjacent behavior, and confirm on independent representative work. A preference for revised prose does not establish a foundational correction. User authority and adopted portable requirements outrank house preference; safety, correctness, and honest evidence outrank brevity or the desire to finish.

Bundled scripts are optional deterministic reporters. Run one only when it owns an observation needed for the live decision, use its `--help` as the invocation contract, and never treat its output as a policy or quality verdict.
