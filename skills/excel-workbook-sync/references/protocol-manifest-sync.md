# Manifest-Driven Sync Protocol

Use the launcher and PowerShell sync surface when repo artifacts and a committed
manifest are the source of truth.

## Commands

```bash
sh <skills-file-root>/scripts/excel-workbook-sync inspect --workbook-path /path/to/workbook.xlsm
sh <skills-file-root>/scripts/excel-workbook-sync query --manifest-path /path/to/excel-sync.manifest.json --surface tables,names,formulas,data-validation,protection,charts,pivots,pq,connections,model
sh <skills-file-root>/scripts/excel-workbook-sync bootstrap --workbook-path /path/to/workbook.xlsx --output-dir /path/to/bundle
sh <skills-file-root>/scripts/excel-workbook-sync push --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-workbook-sync pull --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-workbook-sync roundtrip --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-workbook-sync refresh --manifest-path /path/to/excel-sync.manifest.json --query-name MyQuery
```

## Use This Protocol When

- workbook artifacts are already committed in the repo
- `excel-sync.manifest.json` defines the intended structure
- you need write-capable sync, refresh, or roundtrip behavior

## Notes

- Manifest-driven write flows still require Excel COM.
- `inspect` defaults to a lean metadata surface. Use `query --surface ...`
  when you need Power Query, connections, model, or other heavier read-only
  metadata explicitly.
- Query, inspect, and bootstrap responses include `capabilities`, `warnings`,
  and `unsupported` fields. Read them before assuming a backend can write or
  expose every requested surface.
- In `auto` mode, manifest read flows prefer the OOXML/package backend when
  the requested surfaces do not require live VBA/project/reference access.
- Package-helper execution is bounded; slow package reads fail explicitly
  instead of hanging indefinitely.
- Generic compare and audit outputs distinguish unavailable COM comparison from
  true parity mismatches through `comparisonAvailable`, `comparisonStatus`, and
  nullable `match` fields.
- Read-only manifest inspection/query paths use read-only Excel open intent
  when they need COM, but a workbook that Excel cannot open still reports a
  bounded explicit failure instead of a synthetic parity success.
- Formulas, data-validation, protection, chart, and pivot artifacts are
  currently pull/query metadata surfaces. They are not manifest push surfaces.
- The generic Python CLI is additive. It does not replace this write surface.
- Load the narrower reference for the domain you are changing when needed:
  `manifest.md`, `query.md`, `power-query.md`, `vba-project.md`, or
  `conditional-formatting.md`.
