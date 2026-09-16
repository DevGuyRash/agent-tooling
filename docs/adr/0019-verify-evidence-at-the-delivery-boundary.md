# ADR 0019: Verify evidence at the delivery boundary

## Status

Accepted.

## Context

Across a six-run blind comparison, candidate reports and independent check scripts executed in their authoring workspaces, where a sibling `target/` directory existed. After only the requested `artifact/` directory was collected, report links and scripts still referenced that sibling path. Blind reviewers could inspect retained output, but the advertised executable evidence no longer ran from the submitted artifact. The defect affected several otherwise correct results and helped decide two slight preferences.

Origin-workspace verification proved the computation, not the durability of its handoff.

## Decision

Evidence claims SHALL be evaluated from the boundary the consumer will actually receive. Referenced inputs, links, commands, notebooks, scripts, and generated assets must remain usable there, identify a stable external authority or explicit dependency, or carry a narrower reproducibility claim.

No file layout or copying strategy is prescribed. The required property is a truthful, usable handoff after collection.

Follow-up trials showed that merely stating this property was insufficient: three fresh agents ran their evidence successfully beside an origin-workspace `target/` and all three still shipped checks that failed after artifact-only collection. Delivery validity therefore requires observable proof in a clean consumer view containing exactly the declared deliverable and explicitly declared external dependencies. Reviewer-side access to undeclared common inputs does not satisfy the producer's reproducibility claim.

A later three-run intervention removed unnecessary review activity but exposed a narrower control failure. All three agents checked the artifact while producer-only inputs were still reachable and none established the actual collected boundary. Two artifacts happened to remain usable after an independent clean collection; the third contained 13 links escaping to an undeclared sibling target. One of its own link-check commands had failed and the run still claimed completion. The boundary is therefore an unconditional handoff invariant, and a failed consequential check must reopen the affected completion claim rather than being displaced by later successful checks of another scope.

The Relay follow-up confirmed that this is an output-system property rather than a report-link nit. Two fresh audits became genuinely self-contained only after the requested artifact was tested with producer-only target paths unavailable. A third run could not establish the same boundary after host filtering and incidental target state interfered, so it remained unverified instead of being counted as a successful delivery. The comparison changed the delivery invariant and evidence custody, not the prose used to describe reproducibility.

## Consequences

- A successful local run is insufficient when collection changes path or dependency topology.
- Audits distinguish computational correctness from delivered reproducibility.
- Experiments retain artifact-boundary failures rather than repairing paths after the blind run.
- Portable artifacts may embed inputs, accept explicit input locations, or reference durable external authority according to the task's ownership and duplication constraints.

## Evidence and reopening condition

The rule is grounded in repeated blind-review observations of broken collected evidence. Reopen it if a host supplies a guaranteed collection contract that preserves origin paths or rewrites dependencies with independently verified semantics.
