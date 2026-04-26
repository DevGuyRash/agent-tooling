# Testing

This skill ships verification assets under `<skills-file-root>/tests/fixtures/`.

`references/excel-capability-matrix.json` is the canonical object, backend,
route, support-level, and evidence taxonomy. It is the only source of truth for
what Excel Foundry can do. Capability claims should point to existing test
selectors in that matrix before being treated as checked off, and every matrix
surface should have either direct evidence, a route/plan test, preserve-only
proof, or an explicit host/API limitation.

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

Use external workbooks only in local audit runs, not in committed tests.

If you are adding or changing fixtures, tests, or local corpus behavior for
this skill, first read `<skills-file-root>/DEVELOPMENT.md`.

Use `matrix-audit` when the task is validating copied workbook mutations across
multiple workbooks and you want one aggregate report root.

For opt-in external corpus smoke coverage, set `EXCEL_SYNC_EXTERNAL_ROOTS` to
an `os.pathsep`-separated list of workbook roots or files and run:

```bash
python -m unittest discover -s <skills-file-root>/tests -p 'test_excel_workbook_external_smoke.py'
```

Optional tuning:

- `EXCEL_SYNC_EXTERNAL_GENERIC_LIMIT=3` limits how many discovered workbooks
  run through generic pull/compare smoke.
- `EXCEL_SYNC_EXTERNAL_PACKAGE_LIMIT=3` limits how many package-readable
  workbooks run through package inspect/query/bootstrap smoke.
- `EXCEL_SYNC_EXTERNAL_AUDIT_LIMIT=3` limits how many discovered workbooks run
  through live `audit` and `matrix-audit` smoke.

The external smoke harness copies caller-provided roots into a short temporary
corpus first, then recursively discovers Excel files plus flat export formats
for classification. Workbook smoke assertions run only on workbook formats;
CSV/TXT/ODS entries are classified without pretending they support workbook
package inspection. Output directories use bounded hash-stable slugs so deep
Windows paths do not affect results.

The external smoke harness runs invariant-based assertions and avoids
workbook-specific counts or content expectations.
