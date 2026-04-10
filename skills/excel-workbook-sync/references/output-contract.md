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
- `workbook_structure/formulas.json`
- `workbook_structure/data_validation.json`
- `workbook_structure/protection.json`
- `workbook_structure/charts.json`
- `workbook_structure/pivots.json`
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
  Excel-generated names and excluding live VBA accessibility/component counts
  that OOXML cannot observe
- `summary`, `mismatches`, and `match`: compatibility aliases for `raw`

The `normalized` section also includes filtered-name diagnostics so the
discarded names stay reviewable.

Live VBA accessibility and component counts remain under diagnostics in both
sections. They stay parity-affecting in `raw`, but are excluded from
`normalized` because OOXML only exposes package-level VBA state while COM
exposes the live VBProject surface.

VBA binary hashes are reported under diagnostics. Missing COM-side hashes are
diagnostics, not automatic parity failures.

## Manifest Query / Inspect / Bootstrap

Manifest-driven `query`, `inspect`, and `bootstrap` payloads include:

- `backend`
- `capabilities`
- `warnings`
- `unsupported`

When the workbook is package-readable, query/bootstrap bundles can also include
read-only metadata for formulas, data-validation, workbook or worksheet
protection, charts, and pivots. Backends that cannot provide one of those
surfaces report it under `unsupported`.

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

The markdown matrix summary reports mutation delta as `changed`,
`unchanged`, `skipped`, `timed_out`, or a subprocess status instead of a
pass/fail label.
