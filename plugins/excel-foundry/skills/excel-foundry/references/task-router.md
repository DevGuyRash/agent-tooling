# Task Router

Use this file to choose the workflow lane before reading command details. This
is a heuristic category router, not a capability matrix. The support ledger
remains `references/excel-capability-matrix.json`.

## Routing Loop

WHEN a workbook task starts THEN you SHALL classify the user's intent before
choosing a backend.

WHEN the intent is known THEN you SHALL identify workbook format, existing
workbook complexity, target surfaces, host or cloud requirements, destructive
risk, and secret handling.

WHEN a safe lane cannot satisfy the requested surface THEN you SHALL escalate
to a host/cloud plan or preserve-only result instead of inventing package
support.

After execution, inspect or read back the changed surfaces. Use diff,
bootstrap, or manifest artifacts when governance, auditability, or repo
synchronization matters.

## Intent Lanes

### Polished Authoring Lane

Use for new `.xlsx` workbooks, dashboards, trackers, models, reports, and
templates where layout quality is a primary outcome.

- Prefer Python workbook libraries such as `xlsxwriter` or `openpyxl` for the
  initial authoring mechanism when the workbook is new.
- Use package inspection, formula inventory, table/chart inventory, bootstrap,
  or diff afterward to verify and govern the artifact.
- You SHALL NOT use this lane to rewrite complex existing workbooks when
  preserving pivots, slicers, macros, Power Query, signatures, or opaque
  package parts is important.

### Package CRUD Lane

Use for package-readable `.xlsx` and `.xlsm` files when the target surfaces are
package-supported and can be verified by readback.

Good targets include cells, ranges, sheets, names, formulas, hyperlinks,
dimensions, supported validation and conditional formatting, comments,
protection, print settings, workbook metadata, existing tables, styles, themes,
and bounded chart reference/title edits.

WHEN complex JSON is needed THEN you SHOULD use `--spec-file` instead of
inline shell JSON.

WHEN using PowerShell with comma-separated `--surface` values THEN you SHALL
quote the value as one argument.

### Existing Workbook Edit Lane

Use when the workbook already exists and preserving its current behavior,
formatting, formulas, and opaque internals matters.

- Inspect first with `workbook inspect`, `query`, or `bootstrap`.
- Apply the smallest scoped mutation that satisfies the request.
- Editable user-maintained ranges that may grow or shrink are usually better
  modeled as Excel Tables/ListObjects with structured references. Data
  validation has narrower source rules: if direct structured references or
  dynamic arrays are rejected, use a named range or helper range fed from table
  formulas, then verify row-add expansion in desktop Excel.
- Avoid authoring mechanisms that rewrite the entire workbook unless inspection
  shows the workbook is simple enough or the user accepts that tradeoff.
- Verify by readback and report any unsupported, host-limited, or preserve-only
  surfaces.

### Desktop Excel Lane

Use for `.xls`, `.xlsb`, conversion, repair, compatibility checks, document
inspection, Power Query refresh or mutation, connections, VBA, pivots, slicers,
timelines, scenarios, Goal Seek, Solver, rich charts, shapes, pictures,
controls, Data Model objects, and other host-owned behavior.

WHEN using desktop Excel THEN you SHALL operate on isolated copies for generic
audit or compare flows unless the user explicitly requests direct live mutation.

### Cloud Workbook Lane

Use Microsoft Graph workbook commands for OneDrive or SharePoint workbook
sessions, worksheet/range/name/table/chart/protection operations, and request
planning.

WHEN a cloud command is mutating and `--dry-run` or `--what-if` is supplied
THEN you SHALL return the planned method, URL, redacted headers, and redacted
body without requiring or serializing bearer tokens.

WHEN executing live cloud commands THEN you SHALL require runtime credentials
and tenant/workspace identifiers through the documented environment variables
or explicit arguments.

### Office Automation Lane

Use Office Scripts, Excel JavaScript, or add-in artifacts when the action
belongs inside an Office host or should be handed to a host-side automation
runtime.

Prefer generated plans or artifacts unless the matrix and current host support
a live execution route.

### Semantic And BI Lane

Use Fabric, Power BI, DAX, TMDL, PBIP, TOM/XMLA, and semantic artifact routes
for model definitions, measures, relationships, roles, partitions, refresh,
and DAX execution. This lane maps to the matrix `tom-fabric` route where TOM,
XMLA, or Fabric owns the operation.

Keep tenant tokens and workspace identifiers runtime-only. You SHALL NOT
serialize credentials into manifests, reports, or generated artifacts.

### Preserve-Only Lane

Use for opaque, sensitive, signed, encrypted, or legacy package internals where
safe public mutation is not available.

Inventory and preserve these surfaces. Preserve-only is a valid governed
outcome, not a failed CRUD attempt.

## Completion Criteria

WHEN completing a governed workbook task THEN you SHALL report the selected
lane, the mechanism used, changed state, readback evidence, and any warnings or
limitations that affect the result.

WHEN the task mutates a workbook THEN you SHALL inspect or read back the
changed surfaces before finalizing.

WHEN destructive, host-limited, cloud, secret-bearing, or preserve-only
behavior is involved THEN you SHALL keep that status explicit in the final
operation payload or user-facing summary.

## Known Gotchas

- Package-readable does not mean package-safe to mutate.
- Python authoring libraries are useful for new workbooks but may not preserve
  advanced internals in existing workbooks.
- Desktop Excel COM can lock files; copied workbooks reduce risk during audit
  and compare flows.
- Inline JSON is fragile across shells; prefer `--spec-file` for complex
  payloads.
- PowerShell treats comma-separated values specially; quote `--surface`
  arguments.
- Cloud dry-run plans should not require tokens. Live execution does.
- Preserve-only and host-limited results should be surfaced as governed
  outcomes rather than hidden fallbacks.
