# Manifest

The skill accepts the current manifest shape used by the workbook repo:

- `workbookPath`
- `vbaComponents[]`
- `structure.tablesPath`
- `structure.namesPath`
- `structure.conditionalFormattingPath`
- `structure.sheetsPath`
- `structure.tablesDiscovery`
- `structure.namesDiscovery`
- `structure.conditionalFormattingDiscovery`

Optional project extensions used by this skill:

- `vbaProject.projectPath`
- `vbaProject.referencesPath`
- `powerQuery.queriesDirectory`
- `powerQuery.queriesPath`
- `powerQuery.connectionsPath`
- `powerQuery.modelPath`
- `powerQuery.refreshPath`
- `structure.formulasPath`
- `structure.dataValidationPath`
- `structure.protectionPath`
- `structure.chartsPath`
- `structure.pivotsPath`

`vbaProject.projectPath` stores queryable project/component metadata.

`vbaProject.referencesPath` stores VBA reference metadata and is the mutable
artifact used for VBA reference sync.

`powerQuery.queriesDirectory` stores one `.pq` file per workbook query.

`powerQuery.queriesPath` stores query-level metadata such as file mapping,
connection name, and load metadata.

`powerQuery.connectionsPath` stores safe workbook connection metadata.

`powerQuery.modelPath` stores Data Model table metadata when Excel exposes it.

`powerQuery.refreshPath` stores explicit refresh-related defaults and
refreshable connection metadata without secrets.

The CLI normalizes these inputs into logical surfaces:

- `vba`
- `tables`
- `sheets`
- `names`
- `cf`
- `formulas`
- `data-validation`
- `protection`
- `charts`
- `pivots`
- `pq`
- `connections`
- `model`
- `project`
- `references`

For the plan-centric package path, `plan`, `compare`, and `sync` consume the
same committed manifest and treat the listed artifact paths as per-surface repo
inputs. Current package-backed write surfaces are:

- `workbook`
- `tables`
- `names`
- `formulas`
- `data-validation`
- `cf`
- `protection`
- `dimensions`
- `hyperlinks`
- `comments`
- `print`

Use `query` or `inspect` without a manifest when only workbook discovery is
needed.
