# ADR 0002: Separate semantic policy from deterministic mechanisms

- Status: Accepted
- Date: 2026-08-15

## Decision

Markdown instructions own semantic intent, judgment, sufficiency, and quality policy. Scripts and other executable mechanisms own deterministic inspection, transformation, custody, packaging, and literal interfaces where execution is more reliable than model recreation.

A mechanism may report or enforce a mechanically decidable boundary. It must not infer semantic quality from keywords, headings, file counts, fixed report order, or a finite inventory of concerns, and its successful exit must not be described as proof that an AI-facing policy worked.

## Why

The former Skill Auditor `instruction_shape.sh` could confirm expected words and ordering while an audit still missed a hard executable defect. That was false assurance: the script measured the shape chosen by its author, not whether an agent understood the target or improved a task.

The Split Testing workspace helper exposed the useful opposite boundary. File locking, opaque path allocation, contained-symlink preservation, escaping-link rejection, topology-aware hashing, interrupted-publication recovery, and reveal-after-judgment are deterministic custody responsibilities. Adversarial tests found and fixed real failures in that code without asking the script to create a task, rubric, grade, or winner.

A held-out plugin audit exposed the inverse mistake: auditors treated a deterministic packet assembler as defective because it did not itself produce the semantic triage and review judgment owned by the surrounding skills. Mechanism responsibility must follow the target's declared interface. Keeping policy out of a helper is not missing functionality unless the maker actually made the helper the semantic owner.

[AuditBench](https://alignment.anthropic.com/2026/auditbench/) supplies broader current evidence for the integration boundary: accurate tools did not automatically improve investigator agents, which could underuse them, lose signal in noise, or fail to convert evidence into correct hypotheses. A mechanism and the agent using it therefore need separate evidence before the package can claim the composed capability.

## Consequences

Structural helpers return facts and evidence gaps. The agent interprets those observations against the target's authority and objective. Executable target behavior remains audit evidence and must be exercised when consequential; prose describing a script is not a substitute.

Reopen the allocation of a responsibility when the semantic boundary becomes a literal external contract, or when a supposedly deterministic mechanism cannot reliably enforce or observe the fact it owns. Do not move policy into code merely to make it countable.
