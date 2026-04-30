# Usage

Use this file for command examples after `SKILL.md` or `references/query.md`
has selected the command family.

For intent and lane selection, read `references/task-router.md` first. This
file gives recipes after the task lane is known.

## Entrypoints

- `scripts/excel-foundry`: direct `<resource> <action> [flags]` commands plus
  manifest/artifact synchronization.
- `scripts/excel_workbook_sync.py`: generic extraction, parity compare, and
  copied-workbook audit bundles.
- `scripts/sync-foundry.ps1`: COM-backed manifest push, pull, roundtrip, and
  refresh wrappers.

## Task Recipes

### Create A Polished Workbook

Use the polished authoring lane from `references/task-router.md` for new
`.xlsx` workbooks that need layout, formulas, tables, charts, validation, and
formatting. Python workbook libraries such as `xlsxwriter` or `openpyxl` are
acceptable mechanisms for this lane. After authoring, use Excel Foundry to
inspect, diff, bootstrap, or otherwise govern the resulting workbook.

Recommended verification:

```powershell
sh <skills-file-root>/scripts/excel-foundry workbook inspect `
  --workbook-path path\to\output.xlsx `
  --surface 'workbook,sheets,tables,names,formulas,data-validation,protection,cf,charts,hyperlinks,comments,print,dimensions'
```

### Edit An Existing Workbook Safely

Inspect before mutation, choose the smallest safe edit, then read back the
changed surface. Prefer package CRUD only when the workbook is package-readable
and the target surface is package-supported. Use desktop Excel or a host plan
for host-owned surfaces.

```powershell
sh <skills-file-root>/scripts/excel-foundry workbook inspect `
  --workbook-path path\to\existing.xlsx `
  --surface 'workbook,sheets,tables,names,formulas,charts,pivots,pq,connections,model'

sh <skills-file-root>/scripts/excel-foundry range set `
  --workbook-path path\to\existing.xlsx `
  --sheet Inputs `
  --range-ref A1:B2 `
  --values-json '[[1,2],[3,4]]'
```

### Audit Or Synchronize Workbook Artifacts

Use bootstrap, plan, compare, and sync when workbook state should be represented
as portable artifacts or compared against repo-managed files. Sync remains
dry-run until `--apply` is supplied.

### Route Host-Owned Work

Use desktop Excel for `.xls`, `.xlsb`, conversion, repair, document inspection,
Power Query refresh or mutation, VBA, pivots, slicers, timelines, scenarios,
Goal Seek, Solver, rich visuals, controls, and Data Model work.

Use Graph workbook commands for OneDrive or SharePoint workbook sessions. Use
`--dry-run` to inspect planned requests without live credentials.

Use Fabric, Power BI, DAX, TMDL, PBIP, and semantic artifact routes for
semantic model and BI work.

## Engines

- `auto`: currently resolves to the OOXML path in the generic Python helper
- `ooxml`: parse the workbook package directly
- `com`: drive Excel through PowerShell automation helpers

For the manifest-driven launcher, treat Windows Excel COM as the live backend
for legacy mutation, `.xls`, and `.xlsb`. The package backend now supports
planning, per-surface compare, dry-run sync, and apply mode for the safe OOXML
write surfaces on package-readable `.xlsx` and `.xlsm`: workbook metadata or
calculation settings, names, formulas, data-validation, conditional
formatting, protection, existing table definitions and table-backed cell
regions, guarded sheet structure operations, row and column dimensions,
hyperlinks, comments, and print settings. Desktop routes cover fidelity
mutation for Power Query, connections, pivots, slicers, timelines, Data Model
objects, and rich chart authoring.

## Known Gotchas

- Use `--spec-file` for complex JSON payloads.
- Quote comma-separated `--surface` values in PowerShell.
- Package-readable workbooks can still contain host-owned or preserve-only
  surfaces.
- Python workbook libraries are good new-authoring mechanisms but can rewrite
  packages in ways that are unsuitable for complex existing workbooks.
- Desktop Excel COM can hold file locks; use isolated copies for generic audit
  and compare flows.
- Live cloud execution needs runtime credentials; dry-run planning should
  return redacted request details.

## Generic Audit CLI

This CLI accepts arbitrary Excel workbook inputs for pull, audit, and copied
workbook reporting. Package-backed reads are broadly workbook-agnostic for
package-readable `.xlsx` and `.xlsm`; COM-backed compare still depends on Excel
being able to open the workbook on the current host.

### Pull

Extract workbook artifacts into a file tree.

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py pull `
  --workbook path\to\file.xlsm `
  --output-root out\excel-foundry `
  --engine auto
```

### Compare

Compare COM and OOXML extraction results for the same workbook.

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py compare `
  --workbook path\to\file.xlsm `
  --output-root out\excel-foundry `
  --engine auto
```

### Audit

Copy the workbook into a gitignored work area, mutate the copy, and emit a report.

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py audit `
  --workbook path\to\file.xlsx `
  --output-root .local\excel-foundry `
  --engine auto
```

### Generic output layout

- `normalized.json`
- `workbook_structure/tables.json`
- `workbook_structure/table_mappings.json`
- `workbook_structure/names.json`
- `workbook_structure/conditional_formatting.json`
- `power_query/connections.json`
- `power_query/queries.json`
- `power_query/data_mashup.xml`
- `vba/vbaProject.bin`
- `vba/vba_project.json`
- `vba/vba_references.json`

Audit runs emit:

- `original-copy/`
- `baseline/`
- `post-mutation/`
- `reports/baseline-compare/compare.json`
- `reports/post-mutation-compare/compare.json`
- `reports/mutation-report.json`
- `reports/report.json`

## Manifest Artifact Commands

Use the existing launcher or `sync-foundry.ps1` when committed repo artifacts and
manifests are the source of truth.

```powershell
sh <skills-file-root>/scripts/excel-foundry plan `
  --manifest-path path\to\excel-foundry.manifest.json `
  --surface all-supported `
  --mode push

sh <skills-file-root>/scripts/excel-foundry compare `
  --manifest-path path\to\excel-foundry.manifest.json `
  --surface 'names,formulas,protection'

sh <skills-file-root>/scripts/excel-foundry sync `
  --manifest-path path\to\excel-foundry.manifest.json `
  --surface 'names,formulas,protection' `
  --mode push

sh <skills-file-root>/scripts/excel-foundry sync `
  --manifest-path path\to\excel-foundry.manifest.json `
  --surface 'names,formulas,protection' `
  --mode push `
  --sheet Sheet1 `
  --name MyValue `
  --apply
```

```powershell
powershell -ExecutionPolicy Bypass -File <skills-file-root>/scripts/sync-foundry.ps1 `
  -ManifestPath path\to\excel-foundry.manifest.json `
  -WorkbookPath path\to\file.xlsm `
  -Direction pull
```

Manifest `query`, `inspect`, and `bootstrap` payloads include:

- `capabilities`: read/write/backend availability flags
- `warnings`: fallback and partial-support diagnostics
- `unsupported`: surfaces the selected backend could not provide
- `engineRoutes`: per-surface routing such as package read/write,
  package inventory with `desktop-write`, or artifact generation

The plan-centric package path adds:

- `plan`: per-surface capability, compare, merge, and intended write counts
- `compare`: per-surface `strict`, `normalized`, and `intent` results
- `sync`: dry-run by default with `--apply` required for mutation
- selectors: `--sheet`, `--table`, `--name`, `--name-prefix`, `--query-name`

Current generic metadata surfaces available through query/bootstrap or pull
bundles include tables, names, conditional formatting, formulas,
data-validation, protection, styles, themes, chart metadata, pivot metadata,
Power Query metadata, and VBA metadata where the backend supports them.

Current package-backed write surfaces available through `sync --apply` are:

- workbook metadata or calculation settings
- sheets for guarded structure planning; destructive deletion uses direct
  `sheet delete --destructive`
- tables
- names
- formulas
- data-validation
- conditional formatting
- protection
- dimensions
- hyperlinks
- comments
- print
- styles and themes as exact package XML part replacements

Charts are package-inventoried, and package sync can update existing chart
titles and series references. Rich chart authoring, pivots, slicers,
timelines, Power Query, shapes, pictures, controls, and Data Model surfaces
plan and compare cleanly in the package path and return route metadata for
write-back. Desktop Excel direct commands can create/update/delete shapes,
add/update/delete pictures, update/delete workbook connections, and inventory
controls on copied live workbooks.

## Direct Command Examples

```powershell
sh <skills-file-root>/scripts/excel-foundry workbook capabilities `
  --workbook-path path\to\file.xlsx `
  --deep `
  --documentation

sh <skills-file-root>/scripts/excel-foundry range set `
  --workbook-path path\to\file.xlsx `
  --sheet Inputs `
  --range-ref A1:B2 `
  --values-json '[[1,2],[3,4]]'

sh <skills-file-root>/scripts/excel-foundry graph-workbook range-set `
  --item-id DRIVE_ITEM_ID `
  --session-id SESSION_ID `
  --sheet Sheet1 `
  --range-ref A1:B2 `
  --values-json '[[1,2]]' `
  --dry-run

sh <skills-file-root>/scripts/excel-foundry fabric-semantic-model get-definition `
  --workspace-id WORKSPACE_ID `
  --semantic-model-id MODEL_ID `
  --format TMDL `
  --dry-run
```
