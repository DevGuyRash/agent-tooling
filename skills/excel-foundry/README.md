# Excel Foundry

Excel workbook tooling across one public launcher plus one generic audit helper:

- `scripts/excel-foundry`: the main user-facing CLI for direct workbook commands plus manifest-driven workflows
- `scripts/excel_workbook_sync.py`: generic workbook pull/compare/audit/matrix-audit on safe copies

The generic Python surface accepts arbitrary workbook inputs for pull, audit,
and copied-workbook reporting. Package-backed read flows are broadly
workbook-agnostic for package-readable `.xlsx` and `.xlsm`, while COM-backed
compare remains dependent on Excel being able to open the workbook on the
current host. Fixture assets under `tests/fixtures/` are verification-only and
do not define the public skill contract.

## Generic Audit Commands

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py pull --workbook path\to\file.xlsm --output-root .local\excel-foundry\pull --engine auto
python <skills-file-root>/scripts/excel_workbook_sync.py compare --workbook path\to\file.xlsm --output-root .local\excel-foundry\compare --engine auto
python <skills-file-root>/scripts/excel_workbook_sync.py audit --workbook path\to\file.xlsm --output-root .local\excel-foundry --engine auto --scenario-set full
python <skills-file-root>/scripts/excel_workbook_sync.py matrix-audit --workbook path\to\file1.xlsm --workbook path\to\file2.xlsx --output-root .local\excel-foundry --engine auto --scenario-set full
```

The generic audit output writes:

- workbook structure artifacts including `table_mappings.json`
- workbook structure metadata files for formulas, data validation,
  protection, charts, and pivots even when those surfaces are empty
- Power Query metadata plus per-query `.pq` files when formulas are available
- raw and normalized parity reports, with normalized parity excluding
  clearly internal names and live-VBA-only surface counts
- explicit compare availability reporting via `comparisonAvailable` and
  `comparisonStatus`, so COM open or timeout failures are distinguishable and
  do not get misreported as parity success
  from content mismatches
- a filtered `normalized.json` for agent-facing review while
  `workbook_structure/names.json` preserves raw extracted names
- mutation reports for copied workbooks
- aggregate matrix summaries for multi-workbook audits

## Unified CLI

```powershell
sh <skills-file-root>/scripts/excel-foundry --help
```

Use the launcher for both direct workbook operations and manifest/workspace
sync flows.

Direct workbook commands currently include package-backed or package-fallback
reads and package-backed direct edits for package-readable `.xlsx` and `.xlsm`:

- `workbook inspect|capabilities|create|diff`
- `manifest validate|doctor|migrate`
- `sheet list|create|delete`
- `name list|set|delete`
- `table list|read`
- `query list`
- `cell get|set`
- `range get|set`

Direct workbook commands now also include Excel COM-backed lifecycle and
advanced verbs:

- `workbook save-as|convert|repair|compatibility|document-inspect`
- `workbook links|break-links|repoint-links|safe-export`

- `table get|create|update|delete`
- `query get|set|delete|refresh`
- `connection list|get`
- `chart list|get|create|update|delete`
- `pivot list|get|create|update|delete|refresh`
- `slicer list|get|create|update|delete|clear|set-filter`
- `timeline list|get|create|update|delete|clear|set-range`
- `model inspect`
- `measure list|get|set|delete`
- `relationship list|get|set|delete`
- `hierarchy list|get|set|delete`
- `kpi list|get|set|delete`
- `perspective list|get|set|delete`
- `solver inspect|plan|execute|export`
- `forecast-sheet inspect|plan|create|export`
- `data-table list|get|create|update|delete|inspect|plan`
- `calc-engine inspect|plan|recalculate|export`, `cube-function list|get|inspect|plan`, and `lambda-name list|get|set|delete|inspect|plan`
- `sparkline list|get|create|update|delete|inspect|plan`
- `xml-map inspect|plan|export|import`, `custom-xml inspect|plan|export`, `ole-object inspect|plan|export`, and `external-data-range list|get|create|update|delete|refresh|inspect|plan`
- `workbook-view list|get|create|update|delete|inspect|plan`, `signature inspect|plan`, `encryption inspect|plan`, and `sensitivity inspect|plan`
- `automation inspect|generate|run` with `vba`, `office-script`, `excel-js-api`, `office-addin`, or `artifact-workbook`
- `office-script-live inspect|plan|execute` and `addin-runtime inspect|plan|execute|validate|sideload-plan`
- `graph-workbook inspect|session-create|session-close|worksheet-list|worksheet-get|worksheet-create|worksheet-update|worksheet-delete|range-get|range-set|range-clear|range-format-get|range-format-set|range-format-font-get|range-format-font-set|range-format-fill-get|range-format-fill-set|range-format-protection-get|range-format-protection-set|range-format-border-list|range-format-border-get|range-format-border-set|range-format-autofit-rows|range-format-autofit-columns|name-list|name-get|name-create|name-update|name-delete|table-list|table-get|table-create|table-update|table-delete|table-row-list|table-row-add|table-column-list|table-column-add|table-sort-apply|table-sort-clear|table-filter-apply|table-filter-clear|table-convert-to-range|chart-list|chart-get|chart-create|chart-update|chart-delete|chart-image|chart-set-data|function-call|protection-get|protection-protect|protection-unprotect`
- `fabric-semantic-model list|get|create|update|delete|get-definition|update-definition|export-definition|refresh|execute-dax`
- `model-table list|get|set|delete`, `dax execute|list|get|set|delete`, and `semantic-artifact inspect|export|push`

Use `--spec-json` or `--spec-file` with the mutating advanced verbs.
Use `--dry-run` or `--what-if` with cloud mutating verbs to emit the planned
HTTP request without calling the service. Cloud commands read bearer tokens
only from runtime environment variables: `EXCEL_FOUNDRY_GRAPH_TOKEN`,
`EXCEL_FOUNDRY_FABRIC_TOKEN`, and `EXCEL_FOUNDRY_POWERBI_TOKEN`.

Live host validation is opt-in. Use `EXCEL_FOUNDRY_LIVE_DESKTOP=1` for Excel
COM tests, `EXCEL_FOUNDRY_LIVE_CLOUD=1` for Graph/Fabric/Power BI tests, and
add `EXCEL_FOUNDRY_LIVE_MUTATION=1` only for temporary-copy or explicitly
disposable mutation resources.

Use manifest/workspace commands when repo artifacts and a committed
`excel-sync.manifest.json` are the source of truth.

Manifest `inspect`, `query`, and `bootstrap` now expose backend-aware
capabilities, engine-route metadata, and unavailable-surface diagnostics. `inspect` defaults to a
lean metadata surface so real `.xlsm` reads do not pay for Power Query
expansion unless you request it explicitly with `query --surface ...`.
Use `workbook capabilities --deep` to emit the canonical capability ledger:
every major workbook surface gets a category, read lane, write lane, route,
verification method, risk class, and host requirements. Routes include
`package-write`, `partial-package-write`, `desktop-write`,
`automation-write`, `graph-write`, `tom-fabric-write`, and `preserve-only`.
The ledger is derived from `references/excel-capability-matrix.json`, which is
the single source of truth for support status and evidence selectors.
Matrix environment fields (`package`, `desktop`, `graph`, `officeScript`, and
`tomFabric`) state the current support level for each backend even when the
overall surface is host-limited; combine those values with `hostRequirements`
before executing, planning, or preserving a surface.
The plan-centric commands add package-backed capability planning,
per-surface compare, dry-run sync, targeted selectors, and apply mode for
safe OOXML surfaces.
Current package/generic metadata surfaces include sheets, tables, names,
conditional formatting, formulas, data-validation, protection, workbook
metadata, dimensions, hyperlinks, comments, print settings, pivot metadata,
chart metadata, Power Query metadata, and VBA metadata.

Write-capable COM flows still exist for the legacy manifest sync scripts.
OOXML/package parsing now also supports manifest-driven `plan`, `compare`,
and `sync` for a safe subset of OOXML surfaces on package-readable `.xlsx`
and `.xlsm` workbooks. Current package-backed write/sync surfaces are workbook
metadata/calculation settings, names, formulas on explicit cell addresses,
data validation, conditional formatting, workbook or worksheet protection,
row and column dimensions, hyperlinks, comments, print settings, and updates
to existing table definitions and table-backed cell regions. Direct
package-backed workbook edits now also support workbook create, workbook diff,
sheet create/delete with `--destructive`, named range edits, cell writes, and
range writes. Package responses include `engineRoutes`; Power Query,
connections, pivots, slicers, timelines, and Data Model surfaces route
write-back to desktop Excel while remaining inspectable, diffable, and
plan-visible from package mode. Automation generation can emit VBA, Office
Scripts, Excel JS/Add-in scaffolds, and Codex artifact-workbook builders;
non-VBA runs return an explicit runner plan rather than trying to execute in
the wrong host.
Desktop-backed lifecycle commands now add:

- structured `save-as` / `convert` flows for `.xlsx`, `.xlsm`, `.xlsb`, `.xls`, `.csv`, `.txt`, and `.ods`
- repair/extract recovery copies using Excel's corrupt-load open modes
- heuristic compatibility reports before lossy conversions
- document-inspector style scans that combine Excel `DocumentInspectors` with manual checks for comments, hidden sheets, hyperlinks, custom properties, and external links
- outbound link inventory, selective link breaking/repointing, and share-safe export copies that sanitize document information on a copy

Generic `excel_workbook_sync.py --engine auto` currently resolves to the OOXML
path first. COM remains available when explicitly requested, and generic
COM-backed read flows still use isolated workbook copies so read reliability
does not depend on the original workbook path staying directly openable by
Excel.
