# Agentic Design & Evaluation

Design useful AI instructions and context, assess delivered skills and plugins, and obtain comparative evidence across domains. Four independently callable entries share one complete foundation:

| Entry | Use it for |
| --- | --- |
| [Prompt and Context Design](skills/prompt-context-design/SKILL.md) | Writing, revising, or assessing prompts and context; instruction content for new skills; continuity and delegation. |
| [Skill Auditor](skills/skill-auditor/SKILL.md) | Reviewing an existing skill or plugin's instructions, discovery, resources, composition, execution, and usefulness. |
| [Split Testing](skills/split-testing/SKILL.md) | Designing, conducting, and interpreting a genuine comparison, including non-AI work. This is the sole maintained owner of comparative methodology. |
| [Foundational Knowledge](skills/foundational-knowledge/SKILL.md) | Understanding the shared knowledge and the governing architecture's authoring scope. |

A request to write a prompt can finish with the prompt. Ordinary draft checking is part of authoring. A comparison that needs new observations includes obtaining them when authorized and feasible.

## Shared knowledge

The governing architecture applies when creating or revising instructions for another AI, including an execution plan. The foundation supplies explanatory knowledge for delegation and evaluation.

Read these public shared resources directly as needed:

| Public resource | Responsibility |
| --- | --- |
| [Foundational knowledge](skills/foundational-knowledge/references/foundational-knowledge.md) | Complete explanatory knowledge and its navigation. |
| [Governing architecture](skills/foundational-knowledge/references/governing-architecture.md) | The separate charter for authoring AI instructions. |
| [Portable skill format](skills/skill-auditor/references/open-standard.md) | Portable-format claims and their distinction from host behavior. |
| [Host delivery](skills/skill-auditor/references/host-contracts.md) | Ingestion, publication, installed resources, and actual consumer boundaries. |

Install the complete plugin. Extracting an individual task-skill directory is unsupported because it omits required shared resources; the dependent entries declare that requirement in `compatibility`. A missing required resource is an incomplete installation, not evidence that its guidance was applied. Generated prompts, plans, and skills have their own delivery boundary and carry the original grounds, constraints, and resources their executors need. They do not depend on this plugin or the author's conversation by default.

## Hosts and optional tools

Both Codex and Claude Code are supported through this repository's host manifests and marketplaces. Available tools and authority depend on the selected host and assignment.

Skill Auditor includes four optional [structural reporters](skills/skill-auditor/references/reporter-tools.md). They use a POSIX shell, standard Unix utilities, and Python 3's standard library. They install nothing and do not modify the target. Reporter success is a bounded structural observation, not evidence of semantic effectiveness. Repository selection and release policy remain in repository tooling.

Friction Diagnostics is installed separately for incident capture and mending. Its records can inform an authorized investigation.

## Installation migration

This package replaces the plugin identities `skill-auditor` and `split-testing`. Install and verify `agentic-design-and-evaluation@agent-tooling` on each intended host before removing those two selected obsolete installations. Preserve unrelated plugins and scopes. Existing sessions may retain the former cached instructions; use a fresh session to see the newly installed catalog.

For this repository, use `scripts/install-all --include agentic-design-and-evaluation` from the repository root after publication to its canonical GitHub marketplace. Omit `--source` for normal installation. The installer bootstraps selected packages; removing old catalog entries does not automatically remove old installed identities. Follow the repository's explicit selected-retirement procedure and host CLI discovery rather than editing caches by hand.

## Evidence and limits

Structural tests cover metadata, source reachability, packaged-resource preservation, and reporter behavior. They do not grade instruction quality. The release's design rationale and qualification evidence are recorded in the repository documentation. A successful explicit task, rendered catalog, native install, or physical resource check supports its own boundary; none alone establishes implicit routing reliability, a particular reading path, general behavioral superiority, or long-horizon effectiveness.
