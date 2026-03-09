# Profile Rules

The same product philosophy applies across hosts, but evaluation details change
by profile.

## Supported Profiles

| Profile | Typical cues | What changes |
| --- | --- | --- |
| `open-standard` | Relative paths, one-hop references, portable frontmatter | Use only broadly portable skill rules. |
| `claude-skill` | Claude-specific packaging examples or invocation guidance | Expect Claude-specific wording or host assumptions. |
| `codex-skill` | `.agents/skills`, `$skill-name`, `/skills`, `agents/openai.yaml`, `AGENTS.md` layering | Expect layered repo guidance and Codex discovery conventions. |
| `copilot-skill` | Prompt files, always-on instructions, Copilot-specific agent packaging | Expect host-specific discovery or invocation assumptions. |
| `internal-house-style` | Organization-specific policy, wrappers, or naming | Treat rules as local overlays, not universal requirements. |
| `auto` | Mixed or incomplete evidence | Infer carefully and report uncertainty. |

## Detection Rules

You SHALL infer the profile from file locations, frontmatter, examples,
documented host behavior, and ambient repo guidance.
WHEN the evidence clearly matches one host THEN you SHALL name that profile.
WHEN the evidence mixes multiple hosts THEN you SHALL report `auto` and you
SHALL avoid false certainty.
WHEN a rule appears to be house style rather than an open-standard requirement
THEN you SHALL label it as profile-specific.

## Evaluation Guardrails

You SHALL keep open-standard requirements separate from profile overlays.
You SHALL NOT present internal house rules as universal defects.
WHEN relative paths and one-hop references satisfy the open standard THEN you
SHALL treat them as correct by default.
WHEN `AGENTS.md` layering is part of the target environment THEN you SHALL
consider whether ambient guidance is the better primitive.
WHEN explicit slash-command, prompt, or multi-agent workflows are part of the
host environment THEN you SHALL consider them during packaging fit.
WHEN the main value is access to external systems or shared services THEN you
SHALL consider MCP-backed tooling or MCP-backed workflows during packaging fit.
