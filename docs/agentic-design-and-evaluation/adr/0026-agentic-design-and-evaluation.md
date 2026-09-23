# ADR 0026: Deliver four capabilities as one complete plugin

- Status: Superseded by ADR 0027 for capability composition; the complete-plugin distribution boundary remains applicable.
- Scope: Agentic Design & Evaluation packaging and resource ownership

## Context

Prompt authoring, context design, delivered-plugin auditing, and comparative testing need related knowledge while serving distinct requests. Maintaining overlapping guidance in separate packages risks divergence and leaves shared resources outside an individual package's delivery boundary.

## Decision

Ship Prompt and Context Design, Skill Auditor, Split Testing, and Foundational Knowledge as independently callable entries in one complete Agentic Design & Evaluation plugin. Maintain the shared foundation and separate authoring charter once. Split Testing remains the sole maintained owner of comparative methodology. Friction Diagnostics remains separately installed.

The supported installation unit is the complete plugin. Task entries can read the shared resources directly and select adjacent capabilities according to the assignment. Extracting an individual task-skill directory is outside the supported distribution contract.

## Rationale and consequences

The bundle delivers shared dependencies together while preserving distinct task entry points. A prompt edit can finish with the prompt; an audit or comparison is selected when the assignment needs it. Consumers rely on declared resource files rather than copied navigation or methodology.

Both supported hosts receive the complete [package](../../../plugins/agentic-design-and-evaluation/README.md). Installation and resource availability require their own checks; the packaging choice alone does not establish a behavioral advantage or reliable implicit routing.
