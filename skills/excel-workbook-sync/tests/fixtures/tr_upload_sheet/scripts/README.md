# TR Upload Workbook Scripts

## Shared sync framework

TR upload now uses the repo-level Excel sync framework under [`excel/scripts`](/C:/Users/E135328/repos/carvana-workflows/excel/scripts/README.md) with manifest file [`excel/tr_upload_sheet/excel-sync.manifest.json`](/C:/Users/E135328/repos/carvana-workflows/excel/tr_upload_sheet/excel-sync.manifest.json).

## `sync-workbook.ps1`

Pushes or pulls both VBA and workbook-structure artifacts for the TR upload workbook through the shared manifest-driven sync surface.

Usage:

```powershell
powershell -ExecutionPolicy Bypass -Command `
  "& '.\excel\tr_upload_sheet\scripts\sync-workbook.ps1' `
    -WorkbookPath '.\excel\tr_upload_sheet\tr_upload_template.xlsm' `
    -Direction roundtrip"
```

## `sync-vba-to-workbook.ps1`

Compatibility wrapper over `excel/scripts/sync-excel-vba.ps1` for the TR upload manifest.

Usage:

```powershell
powershell -ExecutionPolicy Bypass -Command `
  "& '.\excel\tr_upload_sheet\scripts\sync-vba-to-workbook.ps1' `
    -WorkbookPath '.\excel\tr_upload_sheet\tr_upload_template.xlsm' `
    -Direction push"
```

Convenience mode:

```powershell
powershell -ExecutionPolicy Bypass -Command `
  "& '.\excel\tr_upload_sheet\scripts\sync-vba-to-workbook.ps1' `
    -WorkbookPath '.\excel\tr_upload_sheet\tr_upload_template.xlsm' `
    -Direction pull"
```

Notes:

- The workbook must allow VBA project access from Excel automation.
- The VBA wrapper reads component mappings from the TR upload manifest.
- Run `sync-workbook.ps1` when Defaults tables, names, or conditional formatting also need to be synchronized.

## `benchmark-lines-paste.ps1`

Measures bulk-paste responsiveness for `tbl_invoice_lines`.

Current outputs:

- `PasteReturnMs`: time for the paste call to return
- `LineReadyMs`: time until managed line formulas are ready on the pasted rows
- `DeferredFlushMs`: time until deferred invoice sync completes
- `ExportFlushMs`: time for `AP_BeforeExportFlush` to drain any remaining deferred work

## Regression scripts

- `test-deferred-sheet-exit.ps1`: verifies invoice sync now completes while staying on `AP_INVOICE_LINES_INTERFACE`
- `test-invoice-number-sequencing.ps1`: baseline invoice-number sequencing regression
- `test-invoice-number-interior-edit.ps1`: verifies an interior line edit recomputes later invoice rows after deferred sync
- `test-invoice-number-stock-vin-patterns.ps1`: verifies VIN-style single-line descriptions emit numeric stock invoice numbers without location prefixes
