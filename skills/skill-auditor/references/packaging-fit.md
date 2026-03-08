# Packaging Fit

Packaging fit decides whether the target capability should stay a skill or move
to a better primitive.

## What To Read

You SHALL read the target `SKILL.md`.
You SHALL read only the directly referenced target files that are necessary to
decide packaging.
WHEN the target mentions host-specific conventions THEN you SHALL interpret them
with the active profile rules before making a universal claim.

## Decision Lens

Ask these questions in order:

1. Is the capability reusable across tasks or repositories?
2. Can activation be described clearly in metadata?
3. Is the value mainly ambient policy, explicit workflow, or executable code?
4. Does the best design combine multiple primitives?

WHEN the content is ambient project guidance, coding policy, or always-on
behavior THEN you SHALL favor `MIGRATE_TO_AGENTS`.
WHEN the capability is an explicit, user-chosen workflow with meaningful
arguments or modes THEN you SHALL favor `MIGRATE_TO_EXPLICIT_PROMPT`.
WHEN the core value is deterministic execution, external data, or generated
artifacts rather than instructions THEN you SHALL favor `MIGRATE_TO_TOOL`.
WHEN reusable expertise should stay on demand and metadata can trigger it well
THEN you MAY keep it as a skill.
WHEN the strongest design splits work between a skill and another primitive
THEN you SHALL use `HYBRID_RECOMMENDED`.

## Verdicts

| Verdict | Use when |
| --- | --- |
| `KEEP_AS_SKILL` | The capability is already a good on-demand skill. |
| `REWORK_AS_SKILL` | The capability should stay a skill but needs metadata or workflow changes. |
| `MIGRATE_TO_AGENTS` | The content should become ambient guidance. |
| `MIGRATE_TO_EXPLICIT_PROMPT` | The capability works better as an explicit prompt, slash command, or MCP workflow. |
| `MIGRATE_TO_TOOL` | The main value belongs in executable code. |
| `HYBRID_RECOMMENDED` | The best answer mixes skill + ambient guidance + explicit prompt + tooling. |

## Output Requirements

You SHALL state one packaging verdict from the allowed set.
You SHALL explain the verdict in one sentence before listing fixes.
WHEN the verdict is not `KEEP_AS_SKILL` or `REWORK_AS_SKILL` THEN you SHALL
stop optimizing the target as a standalone skill.
WHEN migration is recommended THEN you SHALL list the smallest set of content
that should move and the primitive each piece belongs to.
You SHALL include a verification plan that proves the new packaging reduces
false triggers or workflow confusion.

## Common Evidence

- Reuse across tasks or repos
- Need for implicit metadata retrieval
- Need for explicit user choice
- Reliance on scripts, CLIs, or services
- Ambient repo policy or house style

## Anti-Patterns

WHEN a skill mostly restates repo-wide policy THEN you SHALL treat it as a
packaging mistake, not as a metadata problem.
WHEN a skill exists only to wrap one command without reusable expertise THEN
you SHALL treat it as a tool candidate.
WHEN a skill bundles both ambient policy and explicit workflow THEN you SHALL
separate those layers instead of scoring them together.
