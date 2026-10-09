---
name: refactoring
description: "Use when restructuring code without changing its behavior, or when reviewing such a change: splitting modules, giving duplicated rules one home, untangling dependencies, renames and moves. Excludes features, fixes, migrations, and tuning."
---

# Refactoring

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Refactoring changes internal structure while the behavior users, consumers, and operators rely on stays the same. Name that preservation boundary first: public APIs and supported call patterns; outputs, errors, exit status, ordering, and side effects; serialized data, persisted state, protocols, and generated artifacts; contractual timing, concurrency, and resource behavior; extension points and known consumers. Declared or relied-upon behavior stays, and so does a suspected bug, which you name rather than fix.

- Before restructuring, write a characterization test for boundary behavior the change touches that no existing test would fail on if it changed; it goes through the existing entry points, so it passes on the current code from the start and runs unchanged after each step.
- Name the structural problem and the evidence of improvement: a removed dependency edge, one remaining home for a rule or fact, a narrower owner, duplicated decision logic gone. Line counts and a green suite do not show structural value.
- A home that replaces copies of a rule which have drifted apart keeps each consumer's current results; erasing a difference between the copies is a behavior change, not part of the refactor.
- Make one structural change at a time, check the boundary after each, and read the diff for accidental behavior, formatting, generated-file, or dependency changes; tool-driven renames and moves need the same check, because reflection, configuration, serialization, and outside consumers escape tools. Large mechanical changes stay separate from semantic restructuring when that makes review and rollback clearer.
- Use the repository's and language's idioms; an abstraction, pattern, or new file needs a demonstrated problem to solve, and duplication goes only when one authority safely serves every consumer, since incidental similarity needs no shared abstraction.
- When the result needs a changed public contract, a behavior fix, a performance target, or old and new representations side by side, it is no longer a refactor; treat it as what it has become.

Read [preservation surfaces](references/preservation-surfaces.md) when the boundary includes published interfaces, data, concurrency, process-wide state, or side effects.
