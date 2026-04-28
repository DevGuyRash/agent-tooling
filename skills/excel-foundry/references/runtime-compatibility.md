# Runtime Compatibility

Use this file to choose a runtime lane before executing workbook operations.
`references/excel-capability-matrix.json` remains the source of truth for each
surface's support level, route, host requirements, destructive risk, and secret
policy.

WHEN choosing a backend THEN you SHALL read the target surface entries from
`references/excel-capability-matrix.json` and follow their `route`,
environment compatibility fields, and `hostRequirements`.

WHEN a workbook is package-readable `.xlsx` or `.xlsm` and every requested
surface is package-supported THEN you SHOULD prefer the Python package backend
through `scripts/excel-foundry` or `scripts/excel_workbook_package.py`.

The package path can inspect and safely mutate supported OOXML surfaces without
opening Excel. It is the preferred lane for workbook metadata, sheets, cells,
ranges, names, formulas, data validation, conditional formatting, protection,
styles, themes, dimensions, hyperlinks, comments, print settings, existing
tables, and supported chart reference updates where the matrix routes the
surface to `package-write`.

WHEN the workbook is `.xls` or `.xlsb` THEN you SHALL use the desktop route for
read, conversion, compare, and mutation work because those formats are not
package-readable OOXML workbooks.

The PowerShell launchers are `scripts/excel-foundry.ps1`,
`scripts/excel-foundry.cmd`, and the POSIX shim `scripts/excel-foundry`.
Use `pwsh` where available. On Windows hosts without `pwsh`, use Windows
PowerShell with the `.ps1` helper for COM-backed operations.

WHEN a task involves `.xls`, `.xlsb`, conversion, repair, compatibility checks,
safe export, document inspection, complete link handling, refresh, VBA, pivots,
slicers, timelines, Power Query mutation, workbook connections, rich visual
objects, controls, scenarios, Goal Seek, formula dependency tracing, or live
Data Model operations THEN you SHALL require Windows desktop Excel through the
COM-backed desktop route unless the matrix marks a different route as supported
for that exact surface.

WHEN using Windows desktop Excel COM THEN you SHALL operate on isolated copies
for generic audit/compare flows, keep Excel hidden unless the user explicitly
needs an interactive host, and report host limitations instead of fabricating
package parity.

WHEN running live desktop tests THEN you SHALL require
`EXCEL_FOUNDRY_LIVE_DESKTOP=1`. WHEN a live desktop test mutates, refreshes,
exports, breaks links, or deletes workbook content THEN you SHALL also require
`EXCEL_FOUNDRY_LIVE_MUTATION=1` and operate only on temporary workbook copies.

WHEN VBA mutation or execution is requested THEN you SHALL require Windows
desktop Excel and Trust Center access to the VBA project object model.

WHEN refreshing Power Query or workbook connections THEN you SHALL require
Windows desktop Excel plus any local providers, drivers, tenant permissions, or
credential stores needed by the workbook. You SHALL NOT serialize credential
material into manifests, fixtures, logs, or reports.

Office Scripts, Excel JavaScript, and Office Add-in lanes currently generate
portable artifacts or runner plans unless the matrix and tests show a live host
execution route for the requested surface.

Microsoft Graph workbook sessions, TOM/XMLA, Fabric REST, PBIP, TMDL, and TMSL
lanes are cloud or semantic-model routes. The unified launcher exposes
host-limited live commands for Graph workbook objects, Fabric semantic model
definitions, Power BI dataset refresh/DAX execution, and local TMDL/TMSL
artifact inventory.

WHEN one of those lanes is selected THEN you SHALL require runtime
authentication, tenant/workspace identifiers, redaction policy, command
surfaces, and evidence selectors before promoting the surface beyond
`partial` or `host-limited` in the matrix.

WHEN a surface cannot be promoted to `supported` THEN you SHALL keep its final
limitation explicit with `closureReason` and `documentationAnchors` in
`references/excel-capability-matrix.json`. Preserve-only and host-limited
closure is acceptable only when the documented route proves inventory,
preservation, diagnostics, or a live host/cloud requirement.

WHEN using live cloud commands THEN you SHALL provide bearer tokens at runtime
through `EXCEL_FOUNDRY_GRAPH_TOKEN`, `EXCEL_FOUNDRY_FABRIC_TOKEN`, or
`EXCEL_FOUNDRY_POWERBI_TOKEN`. You SHALL NOT serialize those tokens into
manifests, fixtures, logs, command output, or definition artifacts.

WHEN running live cloud tests THEN you SHALL require
`EXCEL_FOUNDRY_LIVE_CLOUD=1` plus safe runtime workbook, workspace, dataset, or
semantic model identifiers. WHEN a live cloud test mutates, refreshes, deletes,
or updates service resources THEN you SHALL also require
`EXCEL_FOUNDRY_LIVE_MUTATION=1` and use only explicitly disposable resources.

WHEN a cloud command is mutating and `--dry-run` or `--what-if` is supplied
THEN you SHALL return the planned method, URL, and redacted body without making
the HTTP request.
