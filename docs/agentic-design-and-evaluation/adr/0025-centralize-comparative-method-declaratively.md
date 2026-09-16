# ADR 0025: Centralize comparative method in a declarative skill

- Status: Accepted
- Recorded: 2026-08-31
- Scope: Split Testing implementation and its integration with Skill Auditor

## Context

Comparisons span different domains, hosts, tools, and evidence formats. Shared comparative guidance needs a clear owner while execution arrangements and domain decisions remain appropriate to the actual assignment.

## Decision

Maintain generic comparative methodology in [Split Testing](../../../plugins/agentic-design-and-evaluation/skills/split-testing/SKILL.md) as a declarative skill with focused references. Use the task's available host facilities and native evidence representations when execution or retention is needed.

Callers retain their own domain authority, criteria, and decisions. Split Testing supplies comparative method. The complete-plugin distribution boundary is recorded in [ADR 0026](0026-agentic-design-and-evaluation.md).

## Rationale and consequences

One maintained method avoids drift between callers. Choosing execution and retention mechanisms for the actual task preserves compatibility with different hosts and domains. A fixed workspace runtime would add an interface and operational dependency to every caller, including tasks that can use existing native facilities.

Updates to comparative guidance belong in the skill and its references. Callers consult that guidance while retaining responsibility for the result they need. Task-specific mechanisms remain appropriate when their contribution justifies them.
