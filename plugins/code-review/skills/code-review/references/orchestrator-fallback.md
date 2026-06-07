# Orchestrator Fallback

Use semantic routing first. Treat `target-ref` as an opaque session key: branch name, commit SHA, or literal `HEAD` all work as long as every later command reuses the exact same string. For a fresh isolated session, prefer an unused canonical date leaf via `--repo-root <path> --date <yyyy-mm-dd>`; one canonical date leaf holds one session, so pick another date or clean up the stale leaf if that path already belongs to a different `target-ref`. For an existing session, reuse the exact persisted `session_dir` and the same `target-ref` string instead of pointing `--session-dir` at an ad hoc directory. Keep the orchestrator thin: persist session state, capture the resolved `session_dir`, register one root reviewer ledger for reviewer/full-cycle runs with `mpcr reviewer register --target-ref <same-exact-ref> --session-dir <persisted.session_dir>`, prefer `mpcr reviewer spawn-routed --parent-id <root-reviewer-id> --session-dir <persisted.session_dir>` to materialize the routed reviewer roster, and hand each worker only its dispatch prompt plus relevant policy packs. Use the spawned worker reviewer ID for bound dispatch, not the root anchor. Use `mpcr session reports --recursive` for descendant report retrieval, `mpcr session artifacts` for flat artifact inventory, and `mpcr session cleanup --session-dir <path>` to discard a stale canonical session leaf before reruns.

## orchestrator-root
version: 2026.03.08
Root orchestration anchor for reviewer, applicator, and full-cycle sessions; route, challenge, gate findings, and synthesize without absorbing routed worker investigation.

### Must
- keep the orchestrator thin
- treat the registered root reviewer as the orchestration anchor, not a substitute for routed workers
- spawn or reuse the current route_decision worker roster before expecting synthesis to complete
- use session-bound dispatch with the spawned worker reviewer_id for role-specific prompts
- run a tight 3-voter legitimacy gate for every candidate finding before reviewer synthesis accepts it or applicator edits code
- give each voter only the minimum packet: finding_id/fingerprint, claim, scenario, anchors, call-chain summary, ruled-out neutralizers, and minimal surrounding refs
- treat voter agents as anti-false-positive validators only: no code changes, no artifacts, no extra fan-out
- challenge worker outputs and maintain session state instead of redoing sibling first-hand review
- WHEN the finding count exceeds 8, batch the legitimacy gate by severity tier: BLOCKER findings get isolated voter packets, MAJOR findings batch into groups of ≤ 4, MINOR findings batch into one voter set

### Must Not
- absorb sibling worker scope
- replace spawn-routed with ad hoc root-only review
- treat the root reviewer_id as the default session-bound prompt for every worker
- dump full session artifacts into voter prompts
- let legitimacy voters mutate code, write artifacts, or spawn more helpers

### Checks
- required routed workers are materialized or intentionally skipped with evidence
- root dispatch stays session-aware and does not claim sibling module ownership
- worker-specific prompts use the spawned reviewer_id instead of the root anchor
- findings that proceed have a recorded 2-of-3 legitimacy vote
- findings that fail the vote are recorded as false positives or categorical declines with a compact reason via reviewer/applicator notes
- voter packets stay scoped to the disputed claim and call chain

### Stop When
- the routed reviewer roster is materialized and the orchestrator has handed off or synthesized through the proper worker flow
- each candidate finding is either legitimacy-gated or rejected before the next phase

### Escalate When
- route_decision is missing or inconsistent with the current session
- required worker roles cannot be materialized from the persisted route

## language-detector
version: 2026.03.08
Identify the active implementation languages early so research workers can fetch targeted primary-source guidance once.

### Must
- derive languages from changed files and relevant interfaces
- normalize languages to stable slugs
- flag when public-interface or PR context implies downstream docs or API research
- avoid speculative language guesses when evidence is absent

### Must Not
- emit product findings in place of language classification
- trigger duplicate language research for the same language without new evidence

### Checks
- every detected language has a concrete file or interface signal
- unknown files do not block known-language handoff

### Stop When
- the language roster is stable enough for research fan-out

### Escalate When
- the change cannot be safely reviewed without resolving an unknown generated or embedded language

## language-research
version: 2026.03.08
Fetch current primary-source docs, standards, and idioms for one language so downstream reviewers stop re-browsing the same material.

### Must
- use primary sources first
- prefer official API docs/specs and standards over commentary
- capture the sources and key idioms in the authored report
- record stable URLs or section pointers for external sources
- limit research to guidance relevant to the changed language and routed domains

### Must Not
- restate generic review doctrine instead of language-specific guidance
- repeat research already cached for the same language without a new need

### Checks
- sources are current and language-native
- guidance maps back to routed review concerns
- report.md records stable source citations when external docs were used

### Stop When
- downstream workers have enough language-specific guidance to proceed without re-browsing

### Escalate When
- no trustworthy primary source can be established for a critical language feature

## domain-reviewer
version: 2026.03.08
Own one review domain, produce a full authored report, and persist machine findings without duplicating sibling scope.

### Must
- own exactly the assigned module or delegated sub-scope
- write a full report.md even for no-findings or low-signal outcomes
- walk adjacent code, callers, tests, docs, and PR context when changed lines are insufficient
- prove each surviving claim along the local causal path: identify the upstream precondition that introduces it and the downstream sink, observable effect, or closure path that still survives later guards, normalization, rollback, dedupe, retries, or caller handling
- challenge findings for anchor quality, realism, duplication, actionability, and counterevidence before escalating them
- cite API docs, web sources, or PR evidence in report.md when they materially inform the claim
- either finalize child_findings or record a categorical no-finding outcome before stopping
- record at least one defended non-finding when the domain has findings — an attack surface or invariant explicitly checked and confirmed clean, with the reasoning that rules it out
- write report.md as a coherent narrative with concrete exploit or failure paths, not as a disconnected bullet list

### Must Not
- re-run language research already provided by upstream workers
- re-open already-addressed or low-signal claims
- delegate the same investigation slice twice
- leave first-hand sibling exploration to the orchestrator

### Checks
- claimed_scope and delegated_scope stay disjoint
- surviving findings keep repo anchors and any external sources are cited in report.md
- surviving findings name both the enabling condition and the downstream effect or closure path
- counterevidence from later guards, normalization, rollback, dedupe, retries, or caller behavior is ruled out or documented before escalation
- defended non-findings are documented and non-empty when findings exist
- residual risks explain why work stops or escalates

### Stop When
- the assigned module has a complete report and finalized child_findings
- the assigned scope is out-of-scope or low-signal and that categorical outcome is documented

### Escalate When
- new evidence implies a different routed domain must be delegated
- a major or blocker finding survives challenge

## final-synthesizer
version: 2026.03.08
Worker policy for the `final-synthesis` dispatch role: concatenate descendant reports, preserve recursive counts, and surface only challenged high-signal findings in the parent synthesis.

### Must
- walk descendant reports in stable order
- preserve recursive counts from machine artifacts
- filter out low-signal, duplicate, non-actionable, and already-addressed claims
- keep only findings that still have repo anchors and cited supporting sources where external context mattered
- surface only findings that already cleared the 2-of-3 legitimacy gate or explicitly hand them back to the orchestrator for that gate
- emit an explicit next action: stop, apply, or reopen
- trace cross-domain compound risk chains — findings that interact to amplify risk SHALL be connected in the synthesis narrative, not listed in isolation
- record a severity rationale when child workers assigned different severities to the same underlying defect
- produce a specific push-or-stop recommendation naming blocking findings by ID and stating the concrete ship decision — the recommendation SHALL NOT be generic boilerplate

### Must Not
- invent new evidence
- duplicate leaf findings as fresh discoveries
- reopen loops for weak or already-resolved items
- emit a generic push-or-stop recommendation that does not reference specific finding IDs

### Checks
- final counts match descendant artifacts
- concatenation order is stable
- push-or-stop recommendation is evidence-backed
- surviving items remain traceable to descendant anchors or cited sources
- surviving items retain a recorded legitimacy vote or explicit orchestrator handoff
- compositional risk chains are traced for findings that interact across domains

### Stop When
- the final synthesis is internally consistent and the next action is explicit

### Escalate When
- a surviving blocker or major finding requires reopen