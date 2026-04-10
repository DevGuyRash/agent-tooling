# Output Contract

The generic Python CLI writes agent-readable bundles under the requested
`--output-root`.

## Pull Output

`pull` writes:

- `normalized.json`
- `workbook_structure/tables.json`
- `workbook_structure/table_mappings.json`
- `workbook_structure/names.json`
- `workbook_structure/conditional_formatting.json`
- `power_query/connections.json`
- `power_query/queries.json`
- `power_query/query_files.json`
- `power_query/queries/*.pq` when formulas are available
- `power_query/data_mashup.xml` when present
- `vba/vba_project.json`
- `vba/vba_references.json`
- `vba/vbaProject.bin` when present
- `ooxml-parts/...`

## Compare Output

`compare` writes `compare.json` with:

- `raw`: direct OOXML versus COM comparison
- `normalized`: the same comparison after filtering clearly internal
  Excel-generated names
- `summary`, `mismatches`, and `match`: compatibility aliases for `raw`

The `normalized` section also includes filtered-name diagnostics so the
discarded names stay reviewable.

VBA binary hashes are reported under diagnostics. Missing COM-side hashes are
diagnostics, not automatic parity failures.

## Audit Output

`audit` stages one copied workbook under a timestamped run root and writes:

- `original-copy/`
- `baseline/`
- `post-mutation/`
- `reports/baseline-compare/compare.json`
- `reports/post-mutation-compare/compare.json`
- `reports/mutation-report.json`
- `reports/report.json`

## Matrix Output

`matrix-audit` writes one timestamped run root containing:

- one copied-workbook audit directory per input workbook
- `matrix-summary.json`
- `matrix-summary.md`
