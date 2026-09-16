# Open Agent Skills Contract

You SHOULD use this reference only for portable Agent Skills claims. You SHALL NOT promote host behavior, repository preference, or general engineering advice into the open standard.

`SKILL.md` syntax alone does not assert conformance to this specification. A custom package may use similar files under a different local contract, and a host described as “Codex-style,” “Claude-compatible,” or similar does not inherit an official host or portable requirement by name. You SHOULD establish that the target claims the standard or is actually consumed through that contract before classifying a mismatch as a conformance defect. Where the target's intended consumer is unsettled, report the compatibility risk and the observation that would resolve it.

## Current specification

The canonical rolling [Agent Skills specification](https://agentskills.io/specification) owns the current portable format. Open it when a changed rule could affect a material finding. A current-policy audit may cite that rolling source while retaining the exact consulted revision in temporary evidence when reproducibility matters.

A portable skill is a directory containing `SKILL.md`. That file contains YAML frontmatter followed by Markdown instructions. The specification requires `name` and `description`; it also defines a small set of optional fields. A host or repository may support more, but that support is not portable unless the specification adopts it.

The `name` is the invocation slug. It is 1–64 lowercase ASCII letters, digits, or single hyphens; it does not begin or end with a hyphen, contain consecutive hyphens, or differ from the parent skill directory name. Human-facing title casing belongs in the body or host metadata.

The `description` is nonempty, no longer than 1024 characters, and communicates both what the skill does and when it applies. Its semantic routing quality requires behavioral evidence; the format constraint alone does not establish that the host will retrieve it correctly. When present, `compatibility` is a nonempty string no longer than 500 characters, and `metadata` is a mapping from string keys to string values.

The portable specification describes file references relative to the skill root. A Markdown document's location, an explicit host root, or a particular tool's resolver can define a different operational base; you SHALL establish the intended consumer before attributing that convention to the standard. The bundled reference reporter resolves literal paths from the declaring document, with `<skills-file-root>` as its explicit skill-root notation. That is its bounded scanning convention, not proof of host resolution. You SHALL verify the distribution boundary the target promises: a complete plugin can supply sibling resources, while extracting one skill may lose them. Machine-specific absolute paths are not portable. Optional `scripts/`, `references/`, and `assets/` directories have no portable quality meaning merely because they are present or absent.

The structural helpers can report required-field, slug, path, line-ending, shebang, executable-bit, and broken-reference facts. Interpret permissive-host behavior as a portability question rather than silently rewriting the portable contract.

A host validator can lag the rolling specification or deliberately implement a narrower subset. When a current portable field is rejected by a claimed host, you SHALL preserve both facts: it is not a portable-format defect, but it may still be a real host-compatibility blocker. You SHALL verify the installed validator rather than assuming a clean or failed third-party check defines the standard.

## Recommendations and host contracts

The current [Agent Skills best practices](https://agentskills.io/skill-creation/best-practices) and [evaluation guidance](https://agentskills.io/skill-creation/evaluating-skills) recommend concise instructions, progressive disclosure, real execution, fresh contexts, and comparisons against a baseline. These are evidence-backed authoring recommendations, not additional frontmatter requirements.

[OpenAI skill guidance](https://learn.chatgpt.com/docs/build-skills) and [Anthropic skill guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) describe their own loading, discovery, packaging, and execution surfaces. You SHALL apply a host rule only when the target claims that host or the user asks about it. You SHALL apply repository conventions only through actual adoption.

Broad preferences about report shape, error wording, cold-start time, idempotency, reference depth, TOCs, script style, or evaluation count are not portable specification failures unless a cited contract actually owns them. They may still be material design or host findings when target evidence shows a consequence.
