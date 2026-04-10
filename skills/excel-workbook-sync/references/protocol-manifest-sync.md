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
- Query, inspect, and bootstrap responses include `capabilities`, `warnings`,
  and `unsupported` fields. Read them before assuming a backend can write or
  expose every requested surface.
- Formulas, data-validation, protection, chart, and pivot artifacts are
  currently pull/query metadata surfaces. They are not manifest push surfaces.
- The generic Python CLI is additive. It does not replace this write surface.
- Load the narrower reference for the domain you are changing when needed:
  `manifest.md`, `query.md`, `power-query.md`, `vba-project.md`, or
  `conditional-formatting.md`.
