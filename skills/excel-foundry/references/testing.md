# Testing

This skill ships verification assets under `<skills-file-root>/tests/fixtures/`.

`references/excel-capability-matrix.json` is the canonical object, backend,
route, support-level, and evidence taxonomy. It is the only source of truth for
what Excel Foundry can do. Capability claims should point to existing test
selectors in that matrix before being treated as checked off, and every matrix
surface should have either direct evidence, a route/plan test, preserve-only
proof, or an explicit host/API limitation.

Governance tests also require every surface to carry `documentationAnchors`
and `closureReason`. These fields are the proof trail for closed but not fully
package-supported surfaces, so tests should reject missing anchors, stale
planned backend lanes, or evidence selectors that do not name real tests.

The matrix `package`, `desktop`, `graph`, `officeScript`, and `tomFabric`
fields are the current compatibility state for each backend/environment. Read
those fields even when a surface is `host-limited`; `host-limited` means a
host condition exists, while the per-environment fields say whether that path
is currently supported, partial, preserve-only, planned, not required, or not
applicable.

Use the fixture for:

- launcher smoke checks
- inspect and query shape validation
- capability, warning, and unsupported-surface validation
- per-surface plan and compare validation
- dry-run and apply-mode package sync validation for the supported OOXML
  surfaces, including exact style/theme part replacement and partial chart
  reference updates
- portable pull and compare tests
- live Excel tests on temp copies when COM validation is required
- repeated live roundtrip checks where semantic matching matters more than
  Excel-assigned priority or rule ordering

If you are adding or changing fixtures, tests, or local corpus behavior for
this skill, first read `<skills-file-root>/DEVELOPMENT.md`.

Use `matrix-audit` when the task is validating copied workbook mutations across
multiple workbooks and you want one aggregate report root.
