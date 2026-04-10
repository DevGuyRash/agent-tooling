## Excel Workbook Sync

- OOXML package fallback is still read-only. `push`, `roundtrip`, and `refresh` still require a write-capable Excel COM open.
- `.xls` and `.xlsb` still depend on Excel COM; there is no non-COM parse/write path for those formats.
- OOXML and COM extraction still disagree on some metadata, especially defined-name counts and COM-side VBA SHA coverage.
- The opt-in TR regression scripts still expose workbook-specific live-sync failures that are outside the generic audit path.
