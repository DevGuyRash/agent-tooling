# Software Development Plugin Authoring Contract

These rules apply only under `plugins/software-development/`.

The public catalog is the skill directories listed in this plugin's README and enforced by its contract test. Keep them independently retrievable; do not add an umbrella skill, router skill, hook, agent, command, MCP server, LSP, CI template, Git wrapper, bundled language server, or shared runtime reference.

The `software-foundation` skill is the one shared foundation. It states the design principles every other skill builds on and links nothing. The first line of every other skill's body links it. No skill copies a foundation statement; a skill states in its own domain's terms how those principles land there, so it stays safe to read alone.

Every `SKILL.md` SHALL use a lowercase `name` slug that exactly matches its directory. The H1 and `agents/openai.yaml` display name SHALL be title-cased.

Each description SHALL state the skill's positive activation boundary and its most important near-neighbor exclusion when one exists.

A skill's own references SHALL be linked directly from its `SKILL.md`, loaded only on a stated condition, and SHALL NOT link to another reference.

Every skill SHALL ship `agents/openai.yaml`, `evals/trigger-prompts.json`, and `evals/evals.json`. Trigger and task evidence SHALL cover the skill's material activation, exclusion, composition, and outcome boundaries, including retained named regression probes and resolvable maintainer fixtures. Evaluate observable outcomes and routing, not exact prose, fixed fixture counts, or private reasoning.

Repository conventions, supported versions, public contracts, build wrappers, and configured tools take precedence over generic guidance. Do not require the newest runtime, arbitrary code-size thresholds, blanket design patterns, universal coverage, or proof-of-process transcripts.

Only `skills/rust-panic-audit/scripts/panic_audit.py` may ship executable runtime code. Maintainer tests and eval fixtures stay outside runtime skill resources. Any runtime-surface exception requires an eval-backed rationale in `MAINTAINERS.md` before release.
