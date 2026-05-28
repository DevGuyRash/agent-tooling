---
name: excel-foundry
description: >-
  Inspect, create, diff, document, audit, automate, and sync Excel workbook
  artifacts across package-readable workbooks, safe copies, installed desktop
  Excel, Microsoft Graph workbook APIs, Office Scripts/Add-in hosts, and
  Fabric/Power BI semantic models. Use when the task involves: (1) workbook
  lifecycle or direct commands such as inspect/diagnose/capabilities/create/diff/save-as/
  convert/repair/compatibility/document-inspect, sheet/table/range/cell/name
  edits, links, safe export, formulas, calc, Solver, scenarios, forecasts, data
  tables, or automation artifacts, (2) package inventory or preservation for
  charts, pivots, slicers, timelines, Power Query, connections, XML/custom XML,
  OLE, signatures, encryption, sensitivity, VBA/package metadata, or embedded
  media, (3) desktop Excel host operations, (4) Graph, Office Scripts,
  Office.js/Add-in, Fabric, Power BI, DAX, TMDL, PBIP, or semantic-model
  operations, or (5) manifest/artifact synchronization, audit bundles, parity
  reports, and portable workbook manifests.
---

# Excel Foundry

Use this skill as the governance and routing layer for Excel workbook work and
related cloud or semantic-model surfaces. Route by user intent first, then by
workbook format, surface support, host availability, destructive risk, and
secret handling. Prefer the narrowest reference that matches the task, then run
the launcher shape `<resource> <action> [flags]`.

## Intent Router

- **Choose the task lane**: load
  `<skills-file-root>/references/task-router.md` when deciding whether the
  task is authoring, package CRUD, existing-workbook edit, desktop Excel,
  cloud workbook, Office automation, semantic/BI, or preserve-only work.
- **Discover support or choose a route**: load
  `<skills-file-root>/references/query.md`; use `workbook capabilities --deep`
  or `workbook capabilities --deep --documentation` when support level,
  backend, closure reason, or documentation anchors matter.
- **Inspect, audit, compare, or pull arbitrary workbooks**: load
  `<skills-file-root>/references/protocol-audit.md`.
- **Run direct workbook commands**: load
  `<skills-file-root>/references/query.md` for command groups, flags, and
  examples.
- **Select a backend or host**: load
  `<skills-file-root>/references/runtime-compatibility.md` before choosing
  package, desktop Excel, Graph, Office Scripts, Office.js/Add-in, Fabric, or
  Power BI routes.
- **Use manifest or artifact synchronization**: load
  `<skills-file-root>/references/protocol-manifest-sync.md`.
- **Interpret JSON output, reports, or artifacts**: load
  `<skills-file-root>/references/output-contract.md`.
- **Develop or maintain this skill itself**: read
  `<skills-file-root>/DEVELOPMENT.md`.

## Routing Heuristics

- Treat `references/excel-capability-matrix.json` as the only support ledger.
  It defines each surface's support level, route, backend lanes, closure
  reason, host requirements, secret handling, and documentation anchors.
- Treat Python workbook libraries, direct OOXML, desktop Excel COM, Graph,
  Office-host automation, Fabric, and Power BI as mechanisms selected by the
  task lane. You SHALL NOT present them as separate top-level workflows when
  Excel Foundry is governing the task.
- Prefer package routes for package-readable `.xlsx` and `.xlsm` workbooks
  when the target surfaces are package-supported.
- Prefer Python workbook authoring mechanisms such as `xlsxwriter` or
  `openpyxl` for new polished `.xlsx` workbooks when visual layout, charts,
  tables, formulas, validation, and formatting matter more than preserving
  existing opaque workbook internals. Use Excel Foundry inspection and
  artifacts to govern and verify the result.
- Use desktop Excel routes for `.xls`, `.xlsb`, conversion, repair, refresh,
  VBA, Power Query mutation, connections, pivots, slicers, timelines, rich
  visual objects, controls, scenarios, Goal Seek, and other surfaces whose
  matrix route requires the installed host.
- Use Graph, Office Scripts, Office.js/Add-in, Fabric, Power BI, DAX, TMDL,
  PBIP, and semantic-artifact routes only when the user asks for those hosts or
  the matrix routes the target surface there.
- When mutation is not publicly safe, return inventory, preservation,
  diagnostics, a host/cloud execution plan, or a clear limitation. You SHALL
  NOT invent package mutation for opaque Excel internals.
- Treat tokens, passwords, connection strings, privacy labels, tenant IDs,
  workbook paths, and workbook contents as sensitive runtime data. Redact
  secrets from output and keep destructive/cloud operations on explicit
  `--dry-run`, `--what-if`, `--apply`, or destructive-intent flags as the
  command requires.

## Bundled Commands

- `<skills-file-root>/scripts/excel-foundry`
- `<skills-file-root>/scripts/excel-foundry.cmd`
- `<skills-file-root>/scripts/excel-foundry.ps1`
- `<skills-file-root>/scripts/excel_workbook_sync.py`
- `<skills-file-root>/scripts/excel_workbook_package.py`
