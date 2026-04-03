---
name: Excel Workbook Sync
description: >-
  Inspect, query, and sync Excel workbook artifacts through a manifest-driven
  Windows Excel COM workflow with WSL/POSIX launchers. Use when the task
  involves: (1) Exporting or importing workbook VBA, tables, names, formulas,
  or conditional formatting, (2) Querying or parsing workbook structure into
  structured JSON, (3) Running manifest-driven push, pull, or roundtrip sync on
  a workbook, (4) Driving Windows Excel automation from WSL or another POSIX
  shell, or (5) Any task involving generic Excel workbook artifact sync rather
  than workbook-behavior regression testing.
---

# Excel Workbook Sync

Use this skill to inspect, query, and sync workbook artifacts. Use
`excel-workbook-testing` when the goal is workbook behavior validation or
business-rule regression coverage.

## Start Here

Use the unified launcher for every workflow:

```bash
sh <skills-file-root>/scripts/excel-workbook-sync inspect --workbook-path /path/to/workbook.xlsm
sh <skills-file-root>/scripts/excel-workbook-sync query --manifest-path /path/to/excel-sync.manifest.json --surface tables,names
sh <skills-file-root>/scripts/excel-workbook-sync roundtrip --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-workbook-sync smoke --manifest-path /path/to/excel-sync.manifest.json
```

Windows shell users can call `<skills-file-root>/scripts/excel-workbook-sync.cmd`
or `<skills-file-root>/scripts/excel-workbook-sync.ps1` directly.

## Workflow

1. Inspect or query the workbook first when the artifact surface is unclear.
2. Use `pull` when the workbook is the source of truth.
3. Use `push` when repo artifacts are the source of truth.
4. Use `roundtrip` or `smoke` on a workbook copy before touching a canonical workbook.
5. Hand workbook-behavior assertions to `excel-workbook-testing`.

## Platform Model

The bash/POSIX entrypoint is a first-class CLI. The PowerShell backend is the
Excel automation engine because Excel COM runs on Windows.

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
- Structured inspect/query JSON
- Manifest-driven push/pull/roundtrip flows

## References To Load On Demand

- `<skills-file-root>/references/manifest.md`
- `<skills-file-root>/references/query.md`
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
