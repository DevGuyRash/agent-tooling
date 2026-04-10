# Testing

This skill ships one committed workbook fixture under
`<skills-file-root>/tests/fixtures/`.

Use the fixture for:

- launcher smoke checks
- inspect and query shape validation
- portable pull and compare tests
- live Excel tests on temp copies when COM validation is required

Use external workbooks only in local audit runs, not in committed tests.

Use `matrix-audit` when the task is validating copied workbook mutations across
multiple workbook families and you want one aggregate report root.

Use workbook-family-specific regression scripts only when the task explicitly
targets that workbook family. They are opt-in validation layers, not part of
the generic audit default.
