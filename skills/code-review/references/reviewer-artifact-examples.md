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

## Schema constraints (`mpcr validate --layer hard`)

Hard validation enforces:

- `artifact_id`: exactly 12 lowercase hex characters
- `producer_kind`: SHALL match the worker's registered `worker_kind`
- `schema_version`: SHALL be `"mpcr_artifact.v1"`
- Required top-level fields for `child_findings`: `schema_version`,
  `artifact_kind`, `artifact_id`, `session_id`, `target_ref`, `producer_kind`,
  `policy_version`, `created_at`, `confidence_label`, `confidence_score`,
  `worker_kind`, `role_id`, `module_ids`, `claimed_scope`, `delegated_scope`,
  `research_refs`, `route_revision_refs`, `loaded_policy_refs`, `findings`
- Required top-level fields for `parent_review`: adds `source_artifact_ids`,
  `final_verdict`, `follow_up`, `ship_readiness`, `coverage_summary`,
  `required_now`, `defended_summary`, `residual_risks`
- Each `[[findings]]` entry: `finding_id`, `module_id`, `surface_ids`,
  `severity` (lowercase), `title`, `claim`, `scenario`, `evidence`,
  `recommendation`, `verification`, `anchors`, `fingerprint`,
  `reopen_eligible`, `confidence_label`, `confidence_score`,
  `evidence_strength`, `false_positive_risk`, `actionable`, `duplicate_suspect`
- Each `[[defended_checks]]` entry: `check_id`, `module_id`, `surface_ids`,
  `method`, `claim`, `attempted_counterexample`, `evidence`, `anchors`,
  `confidence_label`, `confidence_score`

## Quality expectations beyond schema

These expectations are not enforced by hard validation but SHALL be met by
all reviewer-mode artifacts:

- Findings SHALL trace both the introducing condition (upstream precondition)
  and the downstream effect (observable impact or closure path).
- `defended_checks` SHALL NOT be empty when findings exist — the absence of
  defended non-findings signals incomplete investigation, not a clean codebase.
- `severity` SHALL be lowercase (`blocker`, `major`, `minor`).
- `recommendation` SHALL be concrete and implementable — not generic advice
  like "add error handling" but specific actions like "subtract `item.quantity`
  instead of 1 at `src/orders.js:16`".
- `report.md` SHALL be a coherent narrative (≥ 200 words) that explains WHY
  each issue is dangerous, not a disconnected bullet list.

## Multi-domain parent reviews

WHEN synthesizing across domains, the `parent_review` SHALL:

- Include a `severity_rationale` field on any `[[required_now]]` finding whose
  severity was changed from the child worker's original assessment.
- Trace compositional risk chains for interacting findings — findings that
  amplify risk when combined SHALL be connected in the synthesis narrative,
  not listed in isolation.
- List all contributing child artifact IDs in `source_artifact_ids`.
