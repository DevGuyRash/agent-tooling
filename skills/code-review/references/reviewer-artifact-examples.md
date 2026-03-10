# Reviewer Artifact Examples

Use these canonical examples when you need to hand-author reviewer-mode artifacts
before running `mpcr validate`, `mpcr reviewer complete-child`, or
`mpcr reviewer finalize`.

- Child findings example: `<skills-file-root>/references/examples/reviewer-child-findings.toml`
- Parent review example: `<skills-file-root>/references/examples/reviewer-parent-review.toml`

Important authoring rule: keep root scalar fields before array-of-table sections
such as `[[loaded_policy_refs]]`, `[[findings]]`, and `[[required_now]]`. TOML
that moves root fields below those sections can parse into the wrong table and
fail validation.
