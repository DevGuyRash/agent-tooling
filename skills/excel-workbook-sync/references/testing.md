# Testing

This skill ships verification assets under `<skills-file-root>/tests/fixtures/`.

Use the fixture for:

- launcher smoke checks
- inspect and query shape validation
- capability, warning, and unsupported-surface validation
- portable pull and compare tests
- live Excel tests on temp copies when COM validation is required
- repeated live roundtrip checks where semantic matching matters more than
  Excel-assigned priority or rule ordering

Use external workbooks only in local audit runs, not in committed tests.

Use `matrix-audit` when the task is validating copied workbook mutations across
multiple workbooks and you want one aggregate report root.
