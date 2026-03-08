# Profile Rules

The same product philosophy applies across hosts, but evaluation details change
by profile.

## Supported Profiles

| Profile | Typical cues | What changes |
| --- | --- | --- |
| `open-standard` | Portable skill folder with `SKILL.md` frontmatter | Use only broadly portable skill rules. |
| `claude-skill` | Host docs or examples specific to Claude-style skills | Expect Claude-specific invocation or packaging conventions. |
| `codex-skill` | `AGENTS.md` layering, `<skills-file-root>`, Codex-style skills | Expect repo guidance layering and on-demand references. |
| `copilot-skill` | Copilot-specific workflow or agent packaging conventions | Expect host-specific discovery or invocation assumptions. |
| `internal-house-style` | Organization-specific policy, wrappers, or naming | Treat rules as local, not universal. |
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
WHEN `AGENTS.md` layering is part of the target environment THEN you SHALL
consider whether ambient guidance is the better primitive.
WHEN explicit slash-command or prompt workflows are part of the host
environment THEN you SHALL consider them during packaging fit.
