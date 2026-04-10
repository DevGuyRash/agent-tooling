# Usage

## Surfaces

- `scripts/excel_workbook_sync.py`: generic extraction, parity compare, and mutation-based audit
- `scripts/excel-workbook-sync` or `scripts/sync-excel.ps1`: manifest-driven sync for push, pull, roundtrip, refresh, and bootstrap

## Engines

- `auto`: prefer COM on Windows when Excel is available, otherwise fall back to OOXML
- `ooxml`: parse the workbook package directly
- `com`: drive Excel through PowerShell automation helpers

## Generic audit CLI

This CLI is intended for arbitrary Excel workbooks. Bundled TR assets are only
fixture coverage for the repo and are not required inputs.

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
  --output-root .local\excel-workbook-sync `
  --engine auto
```

`audit` is generic by default. Workbook-family regression suites are opt-in and
fixture-specific:

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py audit `
  --workbook path\to\fixture.xlsm `
  --output-root .local\excel-workbook-sync `
  --engine auto `
  --include-regressions
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

- `baseline/`
- `mutated/`
- `report.json`

## Manifest-driven sync

Use the existing launcher or `sync-excel.ps1` when committed repo artifacts and manifests are the source of truth.

```powershell
powershell -ExecutionPolicy Bypass -File <skills-file-root>/scripts/sync-excel.ps1 `
  -ManifestPath path\to\excel-sync.manifest.json `
  -WorkbookPath path\to\file.xlsm `
  -Direction pull
```
