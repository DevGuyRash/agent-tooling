# Output Contract

The default output is a concise Improvement Brief that a human maintainer can
act on immediately.

You SHALL include every required section in the default brief.
You SHALL keep the default brief compact enough to read without appendices.
You SHALL include at least one concrete observed prompt, output, or file anchor
in `Key evidence`.
WHEN detailed evidence helps THEN you MAY append eval tables, deterministic
checks, or before/after notes after the default brief.
You SHALL NOT default to a large taxonomy table, a long audit dissertation, or
a script dump.

## Required Template

```markdown
# Skill Improvement Brief: <skill-name>

## Packaging verdict
<KEEP_AS_SKILL | REWORK_AS_SKILL | MIGRATE_TO_AGENTS | MIGRATE_TO_EXPLICIT_PROMPT | MIGRATE_TO_TOOL | HYBRID_RECOMMENDED>

## One-sentence diagnosis
<What is most fundamentally wrong or right>

## Key evidence
- <one prompt, output, or file observation>
- <one prompt, output, or file observation>

## Top issues
1. <issue>
2. <issue>
3. <issue>

## Recommended changes
1. <specific change>
2. <specific change>
3. <specific change>

## Verification plan
- <test>
- <test>
- <test>

## Optional appendices
- Deterministic checks
- Eval cases
- Before/after notes
```

## Briefing Rules

You SHALL lead with the packaging verdict.
You SHALL keep the diagnosis to one sentence.
You SHALL keep `Key evidence` concrete and observed rather than abstract.
You SHALL limit the default issue and change lists to the highest-leverage
items.
You SHALL always include a verification plan.
