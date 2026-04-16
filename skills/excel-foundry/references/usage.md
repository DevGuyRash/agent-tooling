# Usage

## Surfaces

- `scripts/excel_workbook_sync.py`: generic extraction, parity compare, and mutation-based audit
- `scripts/excel-foundry`: manifest-driven inspect/query/bootstrap plus plan/compare/sync and the legacy push/pull/roundtrip/refresh wrappers
- `scripts/sync-excel.ps1`: legacy manifest-driven COM sync for push, pull, roundtrip, and refresh

## Engines

- `auto`: prefer COM on Windows when Excel is available, otherwise fall back to OOXML
- `ooxml`: parse the workbook package directly
- `com`: drive Excel through PowerShell automation helpers

For the manifest-driven launcher, treat Windows Excel COM as the live backend
for legacy mutation, `.xls`, and `.xlsb`. The package backend now supports
planning, per-surface compare, dry-run sync, and apply mode for the safe OOXML
write surfaces on package-readable `.xlsx` and `.xlsm`: names, formulas,
data-validation, conditional formatting, and protection.

## Generic audit CLI

This CLI accepts arbitrary Excel workbook inputs for pull, audit, and copied
workbook reporting. Package-backed reads are broadly workbook-agnostic for
package-readable `.xlsx` and `.xlsm`; COM-backed compare still depends on Excel
being able to open the workbook on the current host. Bundled fixtures are
verification assets for the repo and are not required inputs.

### Pull

Extract workbook artifacts into a file tree.

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py pull `
  --workbook path\to\file.xlsm `
  --output-root out\excel-sync `
  --engine auto
```

### Compare

Compare COM and OOXML extraction results for the same workbook.

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py compare `
  --workbook path\to\file.xlsm `
  --output-root out\excel-sync `
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

## Manifest-driven sync

Use the existing launcher or `sync-excel.ps1` when committed repo artifacts and
manifests are the source of truth.

```powershell
sh <skills-file-root>/scripts/excel-foundry plan `
  --manifest-path path\to\excel-sync.manifest.json `
  --surface all-supported `
  --mode push

sh <skills-file-root>/scripts/excel-foundry compare `
  --manifest-path path\to\excel-sync.manifest.json `
  --surface names,formulas,protection

sh <skills-file-root>/scripts/excel-foundry sync `
  --manifest-path path\to\excel-sync.manifest.json `
  --surface names,formulas,protection `
  --mode push

sh <skills-file-root>/scripts/excel-foundry sync `
  --manifest-path path\to\excel-sync.manifest.json `
  --surface names,formulas,protection `
  --mode push `
  --sheet Sheet1 `
  --name MyValue `
  --apply
```

```powershell
powershell -ExecutionPolicy Bypass -File <skills-file-root>/scripts/sync-excel.ps1 `
  -ManifestPath path\to\excel-sync.manifest.json `
  -WorkbookPath path\to\file.xlsm `
  -Direction pull
```

Manifest `query`, `inspect`, and `bootstrap` payloads include:

- `capabilities`: read/write/backend availability flags
- `warnings`: fallback and partial-support diagnostics
- `unsupported`: surfaces the selected backend could not provide

The plan-centric package path adds:

- `plan`: per-surface capability, compare, merge, and intended write counts
- `compare`: per-surface `strict`, `normalized`, and `intent` results
- `sync`: dry-run by default with `--apply` required for mutation
- selectors: `--sheet`, `--table`, `--name`, `--name-prefix`, `--query-name`

Current generic metadata surfaces available through query/bootstrap or pull
bundles include tables, names, conditional formatting, formulas,
data-validation, protection, chart metadata, pivot metadata, Power Query
metadata, and VBA metadata where the backend supports them.

Current package-backed write surfaces available through `sync --apply` are:

- names
- formulas
- data-validation
- conditional formatting
- protection

Charts, pivots, Power Query, connections, model, and tables still plan and
compare cleanly in the package path, but remain unsupported for package writes.
