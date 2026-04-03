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

`vbaProject.projectPath` stores queryable project/component metadata.

`vbaProject.referencesPath` stores VBA reference metadata and is the mutable
artifact used for VBA reference sync.

The CLI normalizes these inputs into logical surfaces:

- `vba`
- `tables`
- `names`
- `cf`
- `project`
- `references`

Use `query` or `inspect` without a manifest when only workbook discovery is needed.
