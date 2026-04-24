# Testing

This skill ships verification assets under `<skills-file-root>/tests/fixtures/`.

Use the fixture for:

- launcher smoke checks
- inspect and query shape validation
- capability, warning, and unsupported-surface validation
- per-surface plan and compare validation
- dry-run and apply-mode package sync validation for the supported OOXML surfaces
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
an `os.pathsep`-separated list of workbook roots and run:

```bash
python -m unittest discover -s <skills-file-root>/tests -p 'test_excel_workbook_external_smoke.py'
```

Optional tuning:

- `EXCEL_SYNC_EXTERNAL_AUDIT_LIMIT=3` limits how many discovered workbooks run
  through live `audit` and `matrix-audit` smoke.

The external smoke harness recursively discovers only Excel files, runs
invariant-based assertions, and avoids workbook-specific counts or content
expectations.
