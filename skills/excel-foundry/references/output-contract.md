# Output Contract

The generic Python CLI writes agent-readable bundles under the requested
`--output-root`.

## Pull Output

`pull` writes:

- `normalized.json`
- `workbook_structure/sheets.json`
- `workbook_structure/workbook.json`
- `workbook_structure/tables.json`
- `workbook_structure/table_mappings.json`
- `workbook_structure/names.json`
- `workbook_structure/conditional_formatting.json`
- `workbook_structure/formulas.json`
- `workbook_structure/data_validation.json`
- `workbook_structure/protection.json`
- `workbook_structure/charts.json`
- `workbook_structure/pivots.json`
- `workbook_structure/dimensions.json`
- `workbook_structure/hyperlinks.json`
- `workbook_structure/comments.json`
- `workbook_structure/print.json`
- `workbook_structure/styles.json`
- `workbook_structure/themes.json`
- `power_query/connections.json`
- `power_query/queries.json`
- `power_query/query_files.json`
- `power_query/queries/*.pq` when formulas are available
- `power_query/data_mashup.xml` when present
- `vba/vba_project.json`
- `vba/vba_references.json`
- `vba/vbaProject.bin` when present
- `ooxml-parts/...`

`normalized.json` is the agent-facing normalized view. It filters internal
Excel-generated names such as `_xlfn.*`, `_xlpm.*`, and `_xlws.*`, and
includes `nameDiagnostics.filteredInternalNames` so the removed names remain
reviewable. Raw extracted names remain in `workbook_structure/names.json`.

The generic Python CLI now defaults to concise stdout summaries. Use
`--stdout full` when you need the full payload on stdout, or `--result-path`
to persist the full JSON result separately while keeping stdout narrow.

When one of the workbook-structure metadata surfaces is absent, `pull` or
package `bootstrap` still
writes the artifact with an empty payload instead of silently omitting the
file.

## Compare Output

`compare` writes `compare.json` with:

- `comparisonAvailable`
- `comparisonStatus`
- `raw`: direct OOXML versus COM comparison
- `normalized`: the same comparison after filtering clearly internal
  Excel-generated names and excluding live VBA accessibility/component counts
  that OOXML cannot observe
- `summary`, `mismatches`, and `match`: compatibility aliases for `raw`

When COM extraction does not complete, `comparisonAvailable` is `false`,
`comparisonStatus` reports the failure class, and `raw.match`,
`normalized.match`, plus top-level `match` are `null`.

`comDiagnostics` preserves the COM-side failure context. For failed opens this
includes requested and working workbook paths, package-readability context, and
structured read-only open-attempt diagnostics when available.

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
- `engineRoutes`
- `capabilityLedger` when `workbook capabilities --deep` is requested

When the workbook is package-readable, query/bootstrap bundles can also include
metadata for formulas, data-validation, workbook or worksheet protection,
styles, themes, charts, pivots, Power Query, connections, and Data Model
artifacts. Package plans use `engineRoutes` to distinguish package-safe writes
from `partial-package-write` and `desktop-write` surfaces. Styles and themes
are exact XML package part replacements, existing chart title and series
reference edits are partial package writes, and rich chart authoring plus
shapes, pictures, controls, and opaque analytics objects are routed to desktop
Excel.

The deep capability ledger is the generic max-write contract. Each surface has
`readLane`, `writeLane`, `route`, `verify`, `risk`, `canReadHere`,
`canWriteHere`, and `canPreserveHere` so agents can select the strongest safe
write path without hard-coded workbook assumptions.

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

The markdown matrix summary also reports baseline and post-mutation comparison
status strings alongside raw and normalized compare cells. Raw and normalized
compare cells render as `pass`, `fail`, or `n/a`.

The JSON matrix summary mirrors that machine-readable status in
`workbooks[].mutationStatus` and explicit baseline/post-mutation comparison
status plus availability fields. It also includes `slug` plus `relativeRoot`
for each per-workbook audit directory.
