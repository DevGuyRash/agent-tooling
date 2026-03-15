# Reviewer Artifact Examples

Use these canonical examples when you need to hand-author reviewer-mode artifacts
before running `mpcr validate`, `mpcr reviewer complete-child`, or
`mpcr reviewer finalize`.

These are session-bound routed examples, not legacy composite placeholders. The
child example uses `domain-reviewer` with explicit `role_id`, `claimed_scope`,
`delegated_scope`, and finding signal metadata that convergence and reopen
logic rely on.

- Child findings example: `<skills-file-root>/references/examples/reviewer-child-findings.toml`
- Parent review example: `<skills-file-root>/references/examples/reviewer-parent-review.toml`

Important authoring rule: keep root scalar fields before array-of-table sections
such as `[[loaded_policy_refs]]`, `[[findings]]`, and `[[required_now]]`. TOML
that moves root fields below those sections can parse into the wrong table and
fail validation.
