## Excel Workbook Sync

- OOXML package fallback is still read-only. `push`, `roundtrip`, and `refresh` still require a write-capable Excel COM open.
- `.xls` and `.xlsb` still depend on Excel COM; there is no non-COM parse/write path for those formats.
- The next hardening phase is an OOXML normalization or package-write strategy for mutate operations on COM-unopenable workbooks.
