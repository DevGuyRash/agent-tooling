## Excel Workbook Sync

- The live `matrix-audit` run against the repo fixture and external template workbooks was interrupted before completion; rerun it under `.local/excel-workbook-sync/` and review the aggregate report tree.
- Raw OOXML versus COM parity still disagrees on some metadata, especially defined-name counts and COM-side VBA SHA coverage, even after adding normalized parity for clearly internal Excel-generated names.
- OOXML package fallback is still read-only. `push`, `roundtrip`, and `refresh` still require a write-capable Excel COM open.
- `.xls` and `.xlsb` still depend on Excel COM; there is no non-COM parse/write path for those formats.
- The opt-in TR regression scripts still expose workbook-specific live-sync failures that are outside the generic audit path.
