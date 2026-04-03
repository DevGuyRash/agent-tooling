# Manifest

The skill accepts the current manifest shape used by the workbook repo:

- `workbookPath`
- `vbaComponents[]`
- `structure.tablesPath`
- `structure.namesPath`
- `structure.conditionalFormattingPath`
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
- `names`
- `cf`
- `pq`
- `connections`
- `model`
- `project`
- `references`

Use `query` or `inspect` without a manifest when only workbook discovery is needed.
