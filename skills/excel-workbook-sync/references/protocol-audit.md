# Generic Audit Protocol

Use the Python CLI for arbitrary-workbook extraction and copied-workbook audit.

## Commands

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py pull --workbook path\to\file.xlsm --output-root .local\excel-workbook-sync\pull --engine auto
python <skills-file-root>/scripts/excel_workbook_sync.py compare --workbook path\to\file.xlsm --output-root .local\excel-workbook-sync\compare --engine auto
python <skills-file-root>/scripts/excel_workbook_sync.py audit --workbook path\to\file.xlsm --output-root .local\excel-workbook-sync --engine auto --scenario-set full
python <skills-file-root>/scripts/excel_workbook_sync.py matrix-audit --workbook path\to\file1.xlsm --workbook path\to\file2.xlsx --output-root .local\excel-workbook-sync --engine auto --scenario-set full
```

## Default Flow

1. Run `pull` when you need one workbook's extracted artifacts only.
2. Run `compare` when you need OOXML versus COM parity on the current workbook.
3. Run `audit` when you need mutation validation on one copied workbook.
4. Run `matrix-audit` when you need the same audit flow across several copied
   workbooks with one aggregate summary.

## Notes

- Use repo `.local` output roots when the work is repo-local and worth
  preserving.
- Generic audit always copies the workbook before mutating it.
- Raw parity preserves the original extraction surfaces.
- Normalized parity filters clearly internal Excel-generated names such as
  `_xlfn.*`, `_xlpm.*`, and `_xlws.*`.
- Normalized parity also excludes live VBA accessibility and component-count
  differences because OOXML only sees package state while COM sees the live
  VBProject surface.
- Compare results report `comparisonAvailable` and `comparisonStatus`.
  Treat `match: null` as "comparison unavailable", not as a workbook mismatch.
- Query/bootstrap payloads should be read alongside backend `capabilities`,
  `warnings`, and `unsupported` fields instead of assuming COM parity implies
  write support.
- `.xls` and `.xlsb` remain COM-dependent.
