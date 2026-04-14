# Excel Workbook Sync

Excel workbook sync tooling across two surfaces:

- `scripts/excel-workbook-sync`: manifest-driven inspect/query/bootstrap/push/pull/roundtrip/refresh
- `scripts/excel_workbook_sync.py`: generic workbook pull/compare/audit/matrix-audit on safe copies

The generic Python surface is designed for arbitrary workbook use. Fixture assets under
`tests/fixtures/` are verification-only and do not define the public skill
contract.

## Generic Audit Commands

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py pull --workbook path\to\file.xlsm --output-root .local\excel-workbook-sync\pull --engine auto
python <skills-file-root>/scripts/excel_workbook_sync.py compare --workbook path\to\file.xlsm --output-root .local\excel-workbook-sync\compare --engine auto
python <skills-file-root>/scripts/excel_workbook_sync.py audit --workbook path\to\file.xlsm --output-root .local\excel-workbook-sync --engine auto --scenario-set full
python <skills-file-root>/scripts/excel_workbook_sync.py matrix-audit --workbook path\to\file1.xlsm --workbook path\to\file2.xlsx --output-root .local\excel-workbook-sync --engine auto --scenario-set full
```

The generic audit output writes:

- workbook structure artifacts including `table_mappings.json`
- workbook structure metadata files for formulas, data validation,
  protection, charts, and pivots even when those surfaces are empty
- Power Query metadata plus per-query `.pq` files when formulas are available
- raw and normalized parity reports, with normalized parity excluding
  clearly internal names and live-VBA-only surface counts
- explicit compare availability reporting via `comparisonAvailable` and
  `comparisonStatus`, so COM open or timeout failures are distinguishable
  from content mismatches
- a filtered `normalized.json` for agent-facing review while
  `workbook_structure/names.json` preserves raw extracted names
- mutation reports for copied workbooks
- aggregate matrix summaries for multi-workbook audits

## Manifest-Driven Commands

```powershell
sh <skills-file-root>/scripts/excel-workbook-sync --help
```

Use the manifest-driven surface when repo artifacts and a committed
`excel-sync.manifest.json` are the source of truth.

Manifest `inspect`, `query`, and `bootstrap` now expose backend-aware
capabilities and unsupported-surface diagnostics. `inspect` defaults to a
lean metadata surface so real `.xlsm` reads do not pay for Power Query
expansion unless you request it explicitly with `query --surface ...`.
Current generic metadata surfaces include tables, names, conditional
formatting, formulas, data-validation, protection, chart metadata, pivot
metadata, Power Query metadata, and VBA metadata.

Write-capable flows remain explicitly Windows Excel COM only. OOXML/package
parsing is still read-only and is used for pull/query/bootstrap coverage on
package-readable `.xlsx` and `.xlsm` workbooks. Auto backend selection now
prefers the package reader for read-only manifest queries when the requested
surfaces do not require live VBA/project inspection. Generic COM-backed read
flows now use isolated workbook copies so read reliability does not depend on
the original workbook path staying directly openable by Excel.
