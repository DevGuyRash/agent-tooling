# ADR 0002: One shared foundation states the design principles every skill builds on

- Status: Proposed. A trial decides how the foundation reaches an agent before this record is accepted.
- Scope: all software-development skills from 2.1.0, and the always-loaded instruction layer they assume.

## Context

The user ranked the generalized concerns first: "I think the generalized skills are the MOST important to get right as they will apply toe verything and ultimately will help create the best possible code too. SSOT for example, modular, etc." They asked for "foundational things, not one-offs for single skills", for concurrency and async practice considered in every language, for skills that cover new and existing code alike ("We want things done right the first time and when they aren't they should be able to be revised to be right with this plugin"), and for the plugin to work as one system while each skill keeps its own domain.

Before 2.1.0 no skill owned these concerns for ordinary code. Where a method skill touched one (refactoring for one home per rule, concurrency engineering for lifecycles, performance engineering for growth), it loaded only on its own kind of request. A baseline on weak settings found that loading those method skills in full changed nothing measurable, while weak runs failed on the concern itself: rules restated outside their home, per-record work that does not scale, mishandled outages in concurrent calls. The text a model reads while writing ordinary code has to carry the principle.

## Decision

The design principles every skill builds on are stated once, as the Software Development Foundation: preserved behavior, correctness, one home per rule or fact, cohesion and dependency direction, abstraction for a present need, data structures and memory for input growth, failure paths, ownership of what code acquires or starts, batching and overlapping waits, bounded work in flight, deadlines from a stated source, responsive executors, and parallel computation. Each statement describes code that meets it, so the same text governs code being written, changed, reviewed, or revised.

A skill states how those principles land in its domain; a language skill names such things as its platform's way to overlap waits and spread computation, collections that scan or reads that hold the whole input, its error and resource constructs, and the surfaces callers rely on. No skill copies a foundation statement. A skill keeps, in its own domain's terms, the principles that domain must not miss, so it stays safe to read without the foundation.

The requested-language statement stays in rust-development, where its effect was measured, until a placement trial shows the effect holds from a shared home and counter-scenarios show it does not flag legitimate glue, shell pipelines, or embedded SQL in other languages.

How the foundation reaches an agent is open. Three deliveries carry the same text: a plugin-level file that every skill links, a listed skill that every other skill links, and a section of the always-loaded instruction layer. A trial on weak settings compares them, with how often the foundation is read and whether a skill read alone does worse than before.

## Consequences

Routing still rests on the host's listing; the foundation adds no router. A skill's own references stay one hop from its body. Where the plugin ships the foundation, its contract test rejects a skill that copies a foundation statement word for word; in every delivery it pins the requested-language statement to rust-development. When the delivery trial decides, this record names the delivery and its evidence, and the losing deliveries are removed.
