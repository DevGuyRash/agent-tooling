# Excel Workbook Sync

Excel workbook sync tooling for `.xlsx` and `.xlsm` files.

This skill now has two complementary surfaces:

- `scripts/excel-workbook-sync`: the existing manifest-driven sync surface for push, pull, roundtrip, refresh, and bootstrap flows
- `scripts/excel_workbook_sync.py`: a portable audit and extraction surface for generic workbook pull, compare, and mutation-based audit work

The generic Python surface is workbook-agnostic. The bundled TR fixture and its
regression scripts are repo-local verification assets, not part of the
distributed skill contract.

Use the Python CLI for generic inspection and audit work:

```powershell
python skills/excel-workbook-sync/scripts/excel_workbook_sync.py --help
```

Use the launcher or PowerShell sync scripts when repo artifacts and workbook manifests are the source of truth:

```powershell
sh skills/excel-workbook-sync/scripts/excel-workbook-sync --help
```
