---
name: Excel Workbook Sync
description: >-
  Inspect, query, and sync Excel workbook artifacts through a manifest-driven
  Windows Excel COM workflow with WSL/POSIX launchers. Use when the task
  involves: (1) Exporting or importing workbook VBA, tables, names, formulas,
  conditional formatting, or Power Query artifacts, (2) Querying or parsing
  workbook structure into structured JSON, (3) Running manifest-driven push,
  pull, roundtrip, or explicit refresh sync on a workbook, (4) Driving Windows
  Excel automation from WSL or another POSIX shell, or (5) Any task involving
  generic Excel workbook artifact sync rather than workbook-behavior regression
  testing.
---

# Excel Workbook Sync

Use this skill to inspect, query, and sync workbook artifacts. Use
`excel-workbook-testing` when the goal is workbook behavior validation or
business-rule regression coverage.

## Start Here

Use the unified launcher for every workflow:

```bash
sh <skills-file-root>/scripts/excel-workbook-sync inspect --workbook-path /path/to/workbook.xlsm
sh <skills-file-root>/scripts/excel-workbook-sync query --manifest-path /path/to/excel-sync.manifest.json --surface tables,names,pq,connections,model
sh <skills-file-root>/scripts/excel-workbook-sync bootstrap --workbook-path /path/to/workbook.xlsx --output-dir /path/to/bundle
sh <skills-file-root>/scripts/excel-workbook-sync roundtrip --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-workbook-sync refresh --manifest-path /path/to/excel-sync.manifest.json --query-name MyQuery
sh <skills-file-root>/scripts/excel-workbook-sync smoke --manifest-path /path/to/excel-sync.manifest.json
```

Windows shell users can call `<skills-file-root>/scripts/excel-workbook-sync.cmd`
or `<skills-file-root>/scripts/excel-workbook-sync.ps1` directly. The
PowerShell entrypoint accepts the same GNU-style flags shown above and also
accepts native PowerShell forms such as `-ManifestPath` and `-WorkbookPath`.

## Workflow

1. Inspect or query the workbook first when the artifact surface is unclear.
   `inspect` and `query` auto-fallback from Excel COM to package parsing for
   OOXML workbooks when direct COM open fails.
2. Use `bootstrap` to generate a starter manifest plus `workbook_structure`
   and Power Query artifacts for an arbitrary workbook bundle. `bootstrap`
   also auto-fallbacks to package parsing for OOXML workbooks when COM open fails.
3. Use `pull` when the workbook is the source of truth. For OOXML workbooks
   that are package-readable but COM-unopenable on this host, `pull` can still
   export structure and Power Query artifacts through the package fallback path.
4. Use `push` when repo artifacts are the source of truth. `push`,
   `roundtrip`, and `refresh` still require a write-capable Excel COM open.
   When COM cannot open a package-readable workbook, those mutate operations
   fail with an explicit read-only fallback message instead of a raw COM error.
5. Use `roundtrip` or `smoke` on a workbook copy before touching a canonical workbook.
   `smoke` creates and uses its own isolated temp workspace copy of the
   manifest bundle before running `roundtrip` and `inspect`.
6. Hand workbook-behavior assertions to `excel-workbook-testing`.

## Platform Model

The bash/POSIX entrypoint is a first-class CLI. The PowerShell backend is the
Excel automation engine because Excel COM runs on Windows, while package
parsing backs OOXML fallback discovery and bootstrap flows.

- Windows: run the PowerShell backend directly.
- WSL/POSIX on a Windows host: use the POSIX launcher; it owns argument
  parsing, path normalization, and host checks, then bridges to Windows
  PowerShell for the COM step.
- Native Linux without a Windows Excel host is unsupported for Excel automation.

Read `<skills-file-root>/references/wsl-linux.md` when the user is in WSL,
Git Bash, or another POSIX shell on Windows.

## What This Skill Owns

- VBA components and VBA project metadata query surfaces
- Name Manager artifacts: named ranges, named formulas, `LAMBDA` helpers
- Excel tables
- Conditional-format artifacts, including formula rules and major visual rule families
- Power Query M definitions, workbook query metadata, Mashup connections, and model-load metadata
- Explicit Power Query refresh execution with structured per-connection results
- Structured inspect/query JSON
- Manifest-driven push/pull/roundtrip flows

## Current Fallback Boundary

- `inspect`, `query`, `bootstrap`, and manifest-driven `pull` support OOXML
  package fallback for `.xlsx`, `.xlsm`, `.xltx`, `.xltm`, and `.xlam`.
- Package fallback currently covers structure and Power Query export surfaces.
  It is intended for discovery, manifest generation, and artifact pull/export.
- Package fallback is currently read-only. It does not implement package-level
  mutation for `push`, `roundtrip`, or `refresh`.
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

## Bundled Scripts

- `<skills-file-root>/scripts/excel-workbook-sync`
- `<skills-file-root>/scripts/excel-workbook-sync.cmd`
- `<skills-file-root>/scripts/excel-workbook-sync.ps1`

## Validation

Run packaging checks:

```bash
sh <skills-file-root>/../skill-auditor/scripts/spec_check.sh <skills-file-root>
```

Run CLI smoke checks:

```bash
python3 <skills-file-root>/tests/test_excel_workbook_sync.py
```

Run opt-in live Excel verification only on a host with desktop Excel COM:

```bash
EXCEL_SYNC_LIVE=1 python3 <skills-file-root>/tests/test_excel_workbook_sync.py
```
