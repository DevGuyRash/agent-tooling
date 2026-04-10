---
name: Excel Workbook Sync
description: >-
  Inspect, extract, sync, compare, and audit Excel workbook artifacts. Use
  when the task involves: (1) Exporting or importing workbook VBA, tables,
  names, formulas, conditional formatting, or Power Query artifacts, (2)
  Querying workbook structure into structured JSON, (3) Running manifest-driven
  push, pull, roundtrip, or explicit refresh sync on a workbook, (4) Comparing
  OOXML and COM extraction parity, or (5) Auditing workbook mutation behavior
  on safe workbook copies.
---

# Excel Workbook Sync

This skill owns both the existing manifest-driven sync surface and a newer
portable audit/extraction surface.

The generic audit/extraction surface is workbook-agnostic. Any TR-specific
workbook assets in `tests/fixtures/` are verification fixtures only and should
not drive core skill behavior.

## Start Here

Use the manifest-driven launcher when repo artifacts and manifests are the
source of truth:

```bash
sh <skills-file-root>/scripts/excel-workbook-sync inspect --workbook-path /path/to/workbook.xlsm
sh <skills-file-root>/scripts/excel-workbook-sync query --manifest-path /path/to/excel-sync.manifest.json --surface tables,names,pq,connections,model
sh <skills-file-root>/scripts/excel-workbook-sync bootstrap --workbook-path /path/to/workbook.xlsx --output-dir /path/to/bundle
sh <skills-file-root>/scripts/excel-workbook-sync roundtrip --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-workbook-sync refresh --manifest-path /path/to/excel-sync.manifest.json --query-name MyQuery
```

Use the Python CLI when the task is generic extraction, parity comparison, or
mutation-based audit of arbitrary workbook copies:

```powershell
python <skills-file-root>/scripts/excel_workbook_sync.py pull --workbook path\to\file.xlsm --output-root out\excel-sync --engine auto
python <skills-file-root>/scripts/excel_workbook_sync.py compare --workbook path\to\file.xlsm --output-root out\excel-sync --engine auto
python <skills-file-root>/scripts/excel_workbook_sync.py audit --workbook path\to\file.xlsm --output-root .local\excel-workbook-sync --engine auto
```

## Workflow

1. Use `inspect`, `query`, `bootstrap`, `push`, `pull`, `roundtrip`, or `refresh` when you are working from committed manifests and artifact paths.
2. Use the Python CLI `pull` when you need a portable one-off extraction of workbook structure, Power Query metadata, or VBA metadata into a temp or local output root.
3. Use `compare` when you need OOXML versus COM parity checks for tables, names, conditional formatting, queries, and VBA visibility.
4. Use `audit` on a workbook copy when you need to validate that table mappings, conditional formatting, and query metadata still pull cleanly after controlled workbook mutations.
5. Treat workbook-family regression suites as opt-in fixture verification layered on top of the generic audit flow, not as part of the generic feature contract.

## Platform Model

- Windows Excel COM powers the rich live extraction and mutation flows.
- OOXML parsing powers portable extraction and fallback discovery.
- Manifest-driven write flows still rely on the current PowerShell sync surface.
- The Python audit surface is additive; it does not replace the existing manifest sync engine.

## What This Skill Owns

- Manifest-driven workbook sync through the existing launcher and PowerShell scripts
- OOXML workbook extraction for tables, names, conditional formatting, Power Query metadata, and VBA package metadata
- COM extraction for live workbook queries and VBA component metadata
- Workbook parity compare between OOXML and COM surfaces
- Mutation-driven workbook audit on safe copied workbooks

## Fallback Boundary

- Manifest-driven write flows remain COM-dependent for mutation.
- OOXML extraction is read-only and intended for discovery, compare, pull, and audit.
- `.xls` and `.xlsb` still depend on Excel COM.

## References To Load On Demand

- `<skills-file-root>/references/manifest.md`
- `<skills-file-root>/references/query.md`
- `<skills-file-root>/references/power-query.md`
- `<skills-file-root>/references/vba-project.md`
- `<skills-file-root>/references/conditional-formatting.md`
- `<skills-file-root>/references/wsl-linux.md`
- `<skills-file-root>/references/idempotency.md`
- `<skills-file-root>/references/testing.md`
- `<skills-file-root>/references/usage.md`

## Bundled Scripts

- `<skills-file-root>/scripts/excel-workbook-sync`
- `<skills-file-root>/scripts/excel-workbook-sync.cmd`
- `<skills-file-root>/scripts/excel-workbook-sync.ps1`
- `<skills-file-root>/scripts/excel_workbook_sync.py`
- `<skills-file-root>/scripts/extract-com.ps1`
- `<skills-file-root>/scripts/mutate-workbook.ps1`

## Validation

```bash
python3 -m unittest discover -s <skills-file-root>/tests -p 'test_*.py'
```
