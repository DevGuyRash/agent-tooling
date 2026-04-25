---
name: excel-foundry
description: >-
  Inspect, create, diff, document, audit, automate, and sync Excel workbook
  artifacts across package-readable workbooks, safe copies, and manifest
  workspaces. Use when the task involves: (1) Workbook lifecycle or direct
  commands such as inspect/capabilities/create/diff/save-as/convert/repair/
  compatibility/document-inspect, sheet create/delete, links, safe export,
  cell/range get/set, name edits, or automation artifacts, (2) Pulling sheets,
  tables, names, formulas, validation, protection, comments, hyperlinks, print,
  dimensions, charts, pivots, slicers/timelines, Power Query, connections,
  Data Model/DAX, or VBA/package metadata from `.xlsx` or `.xlsm`, (3)
  Comparing OOXML, package, artifact, and Excel COM surfaces, (4) Running
  manifest validate/doctor/migrate or push/pull/roundtrip/refresh/plan/compare/
  sync, or (5) Producing audit bundles, parity reports, and portable workbook
  manifests.
---

# Excel Foundry

Use this skill for four explicit workflows:

- Workbook lifecycle and capability discovery through the unified launcher
- Direct workbook CRUD-style work through the unified launcher
- Generic workbook audit on safe copied workbooks
- Manifest-driven sync where repo artifacts are the source of truth

The generic pull, audit, and reporting flows accept arbitrary workbook inputs.
Package-backed read flows are broadly workbook-agnostic for package-readable
`.xlsx` and `.xlsm`, while COM-backed compare remains contingent on Excel being
able to open the workbook on the current host. Assets under
`<skills-file-root>/tests/fixtures/` are verification fixtures only and do not
define the generic contract.

## Start Here

- If you need `pull`, `compare`, `audit`, or `matrix-audit`, load
  `<skills-file-root>/references/protocol-audit.md`.
- If you need direct workbook commands such as `sheet list`, `sheet create`,
  `sheet delete`,
  `cell get`, `cell set`, `range get`, `range set`, `name set`,
  `workbook inspect`, `workbook capabilities`, `workbook create`,
  `workbook diff`, `workbook save-as`, `workbook convert`,
  `workbook repair`, `workbook compatibility`, `workbook document-inspect`,
  `workbook links`, `workbook break-links`, `workbook repoint-links`,
  `workbook safe-export`,
  `automation generate`, `automation run`, guarded `hierarchy set/delete`,
  `kpi set/delete`, or `perspective set/delete`,
  `manifest validate`, or `manifest migrate`, load
  `<skills-file-root>/references/query.md`.
- If you need `inspect`, `query`, `bootstrap`, `push`, `pull`, `roundtrip`,
  `refresh`, `plan`, `compare`, or `sync` from a committed manifest, load
  `<skills-file-root>/references/protocol-manifest-sync.md`.
- If you need the report shape, artifact layout, or parity semantics, load
  `<skills-file-root>/references/output-contract.md`.
- If you need fixture usage or validation guidance, load
  `<skills-file-root>/references/testing.md`.
- If you are editing, testing, packaging, or reviewing this skill itself, load
  `<skills-file-root>/DEVELOPMENT.md`. Do not load it for normal workbook
  user tasks.

## Workflow Notes

- Generic audit always operates on copied workbooks inside a local output root.
- Treat workbook paths, workbook contents, customer names, IDs, business terms,
  local usernames, and source-system labels as potentially sensitive. Do not
  copy user-specific names or local paths into committed skill files; use
  neutral fixtures and environment-driven local corpora instead.
- Raw and normalized parity both matter. Normalized parity filters clearly
  internal Excel-generated names, and excludes live-VBA-only capability
  counts that OOXML cannot observe, so user-facing mismatches are easier to
  see.
- Standalone `pull` writes a filtered `normalized.json` for agent-facing name
  review, while `workbook_structure/names.json` preserves the raw extracted
  names.
- Manifest-driven query payloads include `capabilities`, `warnings`,
  `unsupported`, and `engineRoutes` fields so agent decisions can follow actual
  backend limits instead of assuming every surface is package-writable.
- `workbook capabilities --deep` emits the canonical capability ledger for the
  current file and host: category, read lane, write lane, route, verification
  method, risk class, and host requirements for each major workbook surface.
- Query/bootstrap coverage now includes sheets, formulas, data-validation,
  protection, workbook metadata, comments, hyperlinks, dimensions, print
  settings, styles, themes, chart metadata, and pivot metadata in the
  manifest contract.
- The plan-centric package path now supports per-surface planning, per-surface
  compare, targeted selectors, dry-run sync, and apply mode for package-safe
  OOXML writes.
- Package routes explicitly distinguish package-safe writes from
  `desktop-write` surfaces such as Power Query, connections, pivots, slicers,
  timelines, and Data Model artifacts; package mode inventories and diffs
  those surfaces without pretending to mutate them.
- Automation is first-class: VBA can run through desktop Excel, while Office
  Scripts, Excel JS/Add-in, and `artifact-workbook` generation return portable
  artifacts or runner plans for their proper host.
- Manifest read flows use bounded package-helper execution and prefer the
  package backend automatically when the requested surfaces do not require live
  VBA/project inspection.
- Generic COM-backed read flows use isolated workbook copies so compare and
  pull do not depend on mutating or directly opening the caller's original
  workbook path.
- Legacy manifest `push`/`pull`/`roundtrip` write flows still rely on Excel
  COM for mutation.
- Package-backed `sync` currently writes names, formulas, data-validation,
  conditional formatting, protection, workbook metadata/calculation settings,
  row and column dimensions, hyperlinks, comments, print settings, exact
  styles/theme part replacement, and updates to existing tables and existing
  chart title/series references for package-readable `.xlsx` and `.xlsm`
  workbooks. Direct package edits also support workbook create, workbook diff,
  sheet create/delete with explicit destructive intent, name updates, and
  cell/range writes. Direct Excel COM
  commands also support workbook
  save-as/convert/repair/compatibility/document-inspect, outbound link
  inventory/break/repoint, share-safe workbook/PDF export copies, table
  create/update/delete, Power Query get/set/delete/refresh, and
  connection/chart/pivot/slicer/timeline listing. They also support live
  shape create/update/delete, picture add/update/delete, control inventory,
  and guarded model hierarchy, KPI, and perspective mutation plans on live
  workbooks.
- `.xls` and `.xlsb` remain COM-dependent.
- Compare output distinguishes unavailable COM comparison from true parity
  mismatches through `comparisonAvailable` and `comparisonStatus`. When Excel
  cannot open a workbook for COM extraction, the compare stays successful but
  reports comparison unavailability instead of synthesizing parity.

## Bundled Commands

- `<skills-file-root>/scripts/excel-foundry`
- `<skills-file-root>/scripts/excel-foundry.cmd`
- `<skills-file-root>/scripts/excel-foundry.ps1`
- `<skills-file-root>/scripts/ExcelFoundry.Common.ps1`
- `<skills-file-root>/scripts/sync-foundry.ps1`
- `<skills-file-root>/scripts/sync-foundry-structure.ps1`
- `<skills-file-root>/scripts/sync-foundry-powerquery.ps1`
- `<skills-file-root>/scripts/sync-foundry-vba.ps1`
- `<skills-file-root>/scripts/excel_workbook_sync.py`
- `<skills-file-root>/scripts/extract-com.ps1`
- `<skills-file-root>/scripts/mutate-workbook.ps1`

## Validation

```bash
python3 -m unittest discover -s <skills-file-root>/tests -p 'test_*.py'
```
