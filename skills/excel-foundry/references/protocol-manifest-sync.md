# Manifest-Driven Sync Protocol

Use the launcher and PowerShell sync surface when repo artifacts and a committed
manifest are the source of truth.

## Commands

```bash
sh <skills-file-root>/scripts/excel-foundry inspect --workbook-path /path/to/workbook.xlsm
sh <skills-file-root>/scripts/excel-foundry workbook inspect --workbook-path /path/to/workbook.xlsx --surface 'workbook,comments,hyperlinks,print,dimensions'
sh <skills-file-root>/scripts/excel-foundry workbook capabilities --workbook-path /path/to/workbook.xlsb
sh <skills-file-root>/scripts/excel-foundry workbook diff --workbook-path /path/to/left.xlsx --other-workbook-path /path/to/right.xlsx --surface 'workbook,sheets,names'
sh <skills-file-root>/scripts/excel-foundry workbook save-as --workbook-path /path/to/source.xlsm --target-path /path/to/copy.xlsb
sh <skills-file-root>/scripts/excel-foundry workbook convert --workbook-path /path/to/source.xlsx --target-format csv
sh <skills-file-root>/scripts/excel-foundry workbook repair --workbook-path /path/to/damaged.xlsx --mode repair --target-path /path/to/damaged.repaired.xlsx
sh <skills-file-root>/scripts/excel-foundry workbook compatibility --workbook-path /path/to/source.xlsm --target-format ods
sh <skills-file-root>/scripts/excel-foundry workbook document-inspect --workbook-path /path/to/source.xlsx
sh <skills-file-root>/scripts/excel-foundry workbook links --workbook-path /path/to/source.xlsx
sh <skills-file-root>/scripts/excel-foundry workbook break-links --workbook-path /path/to/source.xlsx --spec-json '{"all":true}'
sh <skills-file-root>/scripts/excel-foundry workbook repoint-links --workbook-path /path/to/source.xlsx --spec-file /path/to/link-map.json
sh <skills-file-root>/scripts/excel-foundry workbook safe-export --workbook-path /path/to/source.xlsx --target-path /path/to/source.share-safe.xlsx
sh <skills-file-root>/scripts/excel-foundry manifest validate --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-foundry manifest doctor --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-foundry manifest migrate --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-foundry query --manifest-path /path/to/excel-sync.manifest.json --surface 'tables,names,formulas,data-validation,protection,charts,pivots,pq,connections,model'
sh <skills-file-root>/scripts/excel-foundry bootstrap --workbook-path /path/to/workbook.xlsx --output-dir /path/to/bundle
sh <skills-file-root>/scripts/excel-foundry plan --manifest-path /path/to/excel-sync.manifest.json --surface all-supported --mode push
sh <skills-file-root>/scripts/excel-foundry compare --manifest-path /path/to/excel-sync.manifest.json --surface 'names,formulas,protection'
sh <skills-file-root>/scripts/excel-foundry sync --manifest-path /path/to/excel-sync.manifest.json --surface 'names,formulas' --mode push
sh <skills-file-root>/scripts/excel-foundry sync --manifest-path /path/to/excel-sync.manifest.json --surface 'names,formulas' --mode push --apply
sh <skills-file-root>/scripts/excel-foundry push --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-foundry pull --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-foundry roundtrip --manifest-path /path/to/excel-sync.manifest.json
sh <skills-file-root>/scripts/excel-foundry refresh --manifest-path /path/to/excel-sync.manifest.json --query-name MyQuery
```

## Use This Protocol When

- workbook artifacts are already committed in the repo
- `excel-sync.manifest.json` defines the intended structure
- you need write-capable sync, refresh, or roundtrip behavior

## Notes

- Legacy manifest-driven `push`/`pull`/`roundtrip` write flows still require Excel COM.
- `inspect` defaults to a lean metadata surface. Use `query --surface ...`
  when you need Power Query, connections, model, or other heavier read-only
  metadata explicitly.
- `plan` reports per-surface capability, compare status, merge state, state
  file path, and intended write counts before mutation.
- `manifest validate` checks schema shape without requiring all artifact files
  to exist yet; `manifest doctor` adds resolved-path and existence checks.
- `manifest migrate` upgrades older manifests to the current v2 structure
  contract and can be reviewed before writing.
- `compare` is per-surface rather than a single coarse workbook result.
- `sync` is dry-run by default. Add `--apply` to mutate the workbook or repo
  artifacts.
- `sync` selectors currently support `--sheet`, `--table`, `--name`,
  `--name-prefix`, and `--query-name`.
- Query, inspect, and bootstrap responses include `capabilities`, `warnings`,
  `unsupported`, and `engineRoutes` fields. Read them before assuming a
  backend can write or expose every requested surface.
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
- Package-backed `sync` currently writes workbook metadata/calculation
  settings, names, formulas, data-validation, conditional formatting,
  protection, row and column dimensions, hyperlinks, comments, print settings,
  exact styles/theme package part replacements, updates to existing tables,
  and existing chart title/series reference updates for package-readable
  `.xlsx` and `.xlsm` workbooks.
- Rich chart authoring, pivots, slicers, timelines, Power Query, connections,
  and model remain compare or plan surfaces in the package path. When a write
  requires desktop Excel, the package plan reports the required route instead
  of attempting a lossy rewrite.
- The generic Python CLI is additive. It does not replace this write surface.
- Load the narrower reference for the domain you are changing when needed:
  `manifest.md`, `query.md`, `power-query.md`, `vba-project.md`, or
  `conditional-formatting.md`.
