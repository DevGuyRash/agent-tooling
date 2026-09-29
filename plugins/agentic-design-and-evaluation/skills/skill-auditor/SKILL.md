---
name: skill-auditor
description: Audit existing skills, plugins, and instruction files for whether each part changes agent behavior for the better at its cost, how they are discovered and loaded, and whether their scripts and resources work.
compatibility: Requires the complete Agentic Design & Evaluation plugin. Optional structural reporters need a POSIX shell, standard Unix tools, and Python 3; behavior trials use the Split Testing trial runtime.
---

# Skill Auditor

An audit gives each unit of the target a verdict (keep, cut, move, or rewrite) with its evidence, as described in [auditing](references/auditing.md). Reading produces hypotheses; behavior trials decide them. A sound target is a valid result.

An audit request alone does not authorize changing the target or the user's installations; changes the mandate includes go ahead, and repairs to instructions follow the [authoring guidance](../foundational-knowledge/references/governing-architecture.md). You SHALL NOT present a verdict about behavior as observed unless a trial observed it.
