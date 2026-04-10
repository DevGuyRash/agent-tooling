---
name: Excel Workbook Sync
description: >-
  Inspect, extract, compare, audit, and sync Excel workbook artifacts across
  safe workbook copies and manifest-driven workspaces. Use when the task
  involves: (1) Pulling tables, names, conditional formatting, formulas,
  data-validation, protection, chart metadata, pivot metadata, Power Query,
  or VBA metadata from `.xlsx` or `.xlsm` workbooks, (2) Comparing OOXML and
  Excel COM extraction surfaces, (3) Auditing workbook mutations on copied
  workbooks, (4) Running manifest-driven push, pull, roundtrip, or refresh
  flows, or (5) Producing agent-readable audit bundles and parity reports.
compatibility: >-
  Windows Excel COM is required for live mutation, `.xls` and `.xlsb`, and
  manifest-driven write flows. OOXML/package pull, query, and bootstrap work
  portably for `.xlsx` and `.xlsm`, but remain read-only.
---

# Excel Workbook Sync

Use this skill for one of two explicit workflows:

- Generic workbook audit on safe copied workbooks
- Manifest-driven sync where repo artifacts are the source of truth

The skill is workbook-agnostic by default. Assets under
`<skills-file-root>/tests/fixtures/` are verification fixtures only and do not
define the generic contract.

## Start Here

- If you need `pull`, `compare`, `audit`, or `matrix-audit`, load
  `<skills-file-root>/references/protocol-audit.md`.
- If you need `inspect`, `query`, `bootstrap`, `push`, `pull`, `roundtrip`, or
  `refresh` from a committed manifest, load
  `<skills-file-root>/references/protocol-manifest-sync.md`.
- If you need the report shape, artifact layout, or parity semantics, load
  `<skills-file-root>/references/output-contract.md`.
- If you need fixture usage or validation guidance, load
  `<skills-file-root>/references/testing.md`.

## Workflow Notes

- Generic audit always operates on copied workbooks inside a local output root.
- Raw and normalized parity both matter. Normalized parity filters clearly
  internal Excel-generated names, and excludes live-VBA-only capability
  counts that OOXML cannot observe, so user-facing mismatches are easier to
  see.
- Manifest-driven query payloads now include `capabilities`, `warnings`, and
  `unsupported` fields so agent decisions can follow actual backend limits.
- Query/bootstrap coverage now includes formulas, data-validation,
  protection, chart metadata, and pivot metadata in the manifest contract.
- Manifest-driven write flows still rely on Excel COM for mutation.
- `.xls` and `.xlsb` remain COM-dependent.

## Bundled Commands

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
