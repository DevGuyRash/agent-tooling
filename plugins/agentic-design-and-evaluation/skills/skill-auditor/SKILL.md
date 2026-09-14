---
name: skill-auditor
description: 'Audit an existing skill or plugin as a delivered capability: instructions, discovery, resources, composition, executable behavior, and usefulness. Use for quality reviews and suspected routing, authority, context, packaging, or completion defects. For writing new instruction content or assessing an ordinary prompt, use Prompt and Context Design; ordinary source-code review is outside this skill’s scope.'
compatibility: Optional structural reporters require a POSIX shell and standard Unix tools; reference_check.sh also requires Python 3.
---

# Skill Auditor

You SHALL determine what materially helps or weakens the skill or plugin and what evidence supports retaining, changing, narrowing, or removing it. You SHALL serve the maintainer's actual decision. A sound target and a clean result are valid. Authority for repairs, release decisions, or external effects comes from the task and applicable contracts, not this skill.

You SHOULD assess the target against its purpose, legitimate requirements, actual consumer, and delivered boundary. Source, installed copy, catalog exposure, activation, execution, and downstream use establish different properties. Familiar conventions and passing reporters do not decide semantic quality. An audit request alone does not authorize changing the target or user installations; you SHALL proceed with changes already included in the mandate.

You SHOULD use the complete [foundational knowledge](../foundational-knowledge/references/foundational-knowledge.md) where it informs the assessment: sections 3–5 help distinguish purpose and authority; 8–11 address source access, continuity, and completion; 12–17 address discovery, evidence, and transfer. Its contents remain open to other relevant concerns. You MAY reuse unchanged material still available; you SHOULD recover relevant grounds after context loss or changes. The shared [governing architecture](../foundational-knowledge/references/governing-architecture.md) governs your work when authoring a repair for another AI, and governs a target only through actual adoption.

You SHOULD choose evidence and reading by what could change the maintainer's decision:

- [Instruction design](references/instruction-design.md) for mandate, authority, rigidity, and instruction-system defects.
- [Context and source evidence](references/context-and-source-evidence.md) for loading, original material, references, and continuity.
- [Executable evidence](references/executable-evidence.md) for scripts, hooks, tools, state changes, and delivered outputs.
- [Plugin fit](references/plugin-fit.md) for discovery, sibling composition, package boundaries, and usefulness.
- [Host contracts](references/host-contracts.md) and [portable skills](references/open-standard.md) for the exact adopted consumer or format.
- [Reporter tools](references/reporter-tools.md) when a bundled deterministic observation would help; [repository overlay](references/repo-overlay.md) explains their repository-related source tags.

When a genuine comparison is needed, you SHALL consult the canonical [Split Testing](../split-testing/SKILL.md) guidance with the question, legitimate authority, existing evidence, and actual constraints. You SHALL keep responsibility for the same assignment and use the resulting evidence in it. A straightforward contradiction, ordinary judgment, or small correction does not by itself require a comparative investigation.

You SHALL ground material findings in reachable consequences and retained evidence. You SHALL distinguish a demonstrated failure, a supported risk, and an unverified claim where the difference changes reliance. You SHOULD check repairs at the affected consumer boundary, including adjacent behavior that matters. Missing required verification leaves that obligation incomplete; optional stronger claims can be withheld without expanding the assignment. You SHALL finish with the supported direction, usable evidence and repair when authorized, and consequential remaining limits. No fixed audit sections, finding count, observer panel, or scoring scheme is required.
