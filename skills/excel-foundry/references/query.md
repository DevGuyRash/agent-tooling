# Query

Use this file for direct launcher commands and command discovery. The launcher
shape is:

```text
<resource> <action> [flags]
```

Default output is JSON. Complex mutations use `--spec-json` or `--spec-file`.
Cloud and destructive commands use `--dry-run`, `--what-if`, `--apply`, or
explicit destructive flags as required by the command.

## Core Workbook Commands

- `workbook inspect|capabilities|create|diff`
- `workbook save-as|convert|repair|compatibility|document-inspect`
- `workbook links|break-links|repoint-links|safe-export`
- `manifest validate|doctor|migrate`
- `sheet list|create|hide|unhide|very-hide|reorder|delete`
- `cell get|set`
- `range get|set`
- `name list|set|delete`
- `table list|read|get|create|update|delete`
- `query list|get|set|delete|refresh`
- `connection list|get|update|delete`
- `chart list|get|create|update|delete`
- `shape list|get|create|update|delete`
- `picture list|get|add|update|delete`
- `control list|get`
- `dimension get`
- `hyperlink list|set|delete`
- `comment list`
- `print get`
- `formula list`
- `validation list`
- `protection get`

## Advanced Workbook Commands

- `pivot list|get|create|update|delete|refresh`
- `pivot-chart list|get|create|update|delete|refresh|export`
- `slicer list|get|create|update|delete|clear|set-filter`
- `timeline list|get|create|update|delete|clear|set-range`
- `chart-sheet list|get|create|update|delete|move|rename|export`
- `what-if inspect`
- `scenario list|get|set|delete`
- `goal-seek execute`
- `formula-audit inspect|export`
- `calc-engine inspect|plan|recalculate|export`
- `cube-function list|get|inspect|plan`
- `lambda-name list|get|set|delete|inspect|plan`
- `solver inspect|plan|execute|export`
- `forecast-sheet inspect|plan|create|export`
- `data-table list|get|create|update|delete|inspect|plan`
- `sparkline list|get|create|update|delete|inspect|plan`
- `xml-map inspect|plan|export|import`
- `custom-xml inspect|plan|export`
- `ole-object inspect|plan|export`
- `external-data-range list|get|create|update|delete|refresh|inspect|plan`
- `workbook-view list|get|create|update|delete|inspect|plan`
- `threaded-comment list|get|create|update|delete`
- `signature inspect|plan`
- `encryption inspect|plan`
- `sensitivity inspect|plan`
- `privacy inspect|redact|export`

## Automation And Host Commands

- `automation inspect|generate|run`
- `office-script validate|run-plan`
- `excel-js-api validate|run-plan`
- `office-addin validate|sideload-plan`
- `office-script-live inspect|plan|execute`
- `addin-runtime inspect|plan|execute|validate|sideload-plan`

## Cloud And Semantic Commands

- `graph-workbook inspect|session-create|session-close|worksheet-list|worksheet-get|worksheet-create|worksheet-update|worksheet-delete|range-get|range-set|range-clear|range-format-get|range-format-set|range-format-font-get|range-format-font-set|range-format-fill-get|range-format-fill-set|range-format-protection-get|range-format-protection-set|range-format-border-list|range-format-border-get|range-format-border-set|range-format-autofit-rows|range-format-autofit-columns|name-list|name-get|name-create|name-update|name-delete|table-list|table-get|table-create|table-update|table-delete|table-row-list|table-row-add|table-column-list|table-column-add|table-sort-apply|table-sort-clear|table-filter-apply|table-filter-clear|table-convert-to-range|chart-list|chart-get|chart-create|chart-update|chart-delete|chart-image|chart-set-data|function-call|protection-get|protection-protect|protection-unprotect`
- `fabric-semantic-model list|get|create|update|delete|get-definition|update-definition|export-definition|refresh|execute-dax|operation-get|operation-result`
- `semantic-artifact inspect|export|push`
- `model inspect`
- `model-table list|get|set|delete`
- `model-measure list|get|set|delete`
- `model-relationship list|get|set|delete`
- `model-role list|get|set|delete`
- `model-partition list|get|set|delete`
- `model-expression list|get|set|delete`
- `measure list|get|set|delete`
- `relationship list|get|set|delete`
- `hierarchy list|get|set|delete`
- `kpi list|get|set|delete`
- `perspective list|get|set|delete`
- `dax execute|list|get|set|delete`

## Manifest Artifact Commands

- `inspect`
- `query`
- `bootstrap`
- `plan`
- `compare`
- `sync`
- `push`
- `pull`
- `roundtrip`
- `refresh`

`plan` returns per-surface capability, compare, merge, and intended write
counts before mutation. `compare` returns per-surface `strict`, `normalized`,
and `intent` results for repo artifacts versus the current workbook. `sync` is
dry-run by default and requires `--apply` to mutate supported package-backed
surfaces.

## Common Flags

- `--workbook-path`
- `--other-workbook-path`
- `--manifest-path`
- `--surface all-supported`
- `--surface 'sheets,tables,names,cf,formulas,data-validation,protection,charts,pivots,pq,connections,model,vba,project,references'`
- `--sheet`
- `--table`
- `--name`
- `--name-prefix`
- `--query-name`
- `--connection`
- `--chart`
- `--pivot`
- `--slicer`
- `--timeline`
- `--automation-type`
- `--drive-id`
- `--item-id`
- `--item-path`
- `--session-id`
- `--persist-changes`
- `--workspace-id`
- `--semantic-model-id`
- `--dataset-id`
- `--operation-id`
- `--operation-location`
- `--definition-dir`
- `--format`
- `--dax-query`
- `--dry-run`
- `--what-if`
- `--apply`
- `--address`
- `--range-ref`
- `--value-json`
- `--values-json`
- `--spec-json`
- `--spec-file`
- `--refers-to`
- `--target-path`
- `--target-format`
- `--mode`
- `--destructive`
- `--deep`
- `--documentation`

## Capability Ledger

`references/excel-capability-matrix.json` is the source of truth for support
and compatibility. Its per-environment fields (`package`, `desktop`, `graph`,
`officeScript`, and `tomFabric`) state the current support level for each
backend even when the overall surface is host-limited; combine them with
`hostRequirements` before choosing execute, plan, or preserve behavior.

Use `workbook capabilities --deep --documentation` when an agent needs support
rationale in-band. The response includes matrix documentation anchors and
closure reasons without creating a second support table. A closed surface can
still be `preserve-only` or host-limited when the documented public route only
supports inventory, preservation, diagnostics, or live host execution.

## Examples

- `workbook inspect --workbook-path /path/to/book.xlsx`
- `workbook capabilities --workbook-path /path/to/book.xlsx --deep --documentation`
- `workbook save-as --workbook-path /path/to/book.xlsm --target-path /path/to/book.xlsb`
- `workbook compatibility --workbook-path /path/to/book.xlsm --target-format ods`
- `workbook document-inspect --workbook-path /path/to/book.xlsx`
- `workbook links --workbook-path /path/to/book.xlsx`
- `workbook break-links --workbook-path /path/to/book.xlsx --spec-json '{"all":true}'`
- `workbook repoint-links --workbook-path /path/to/book.xlsx --spec-file /path/to/link-map.json`
- `workbook safe-export --workbook-path /path/to/book.xlsx --target-path /path/to/book.share-safe.xlsx`
- `sheet delete --workbook-path /path/to/book.xlsx --sheet Staging --destructive`
- `range set --workbook-path /path/to/book.xlsx --sheet Inputs --range-ref A1:B2 --values-json '[[1,2],[3,4]]'`
- `what-if inspect --workbook-path /path/to/book.xlsx`
- `scenario set --workbook-path /path/to/book.xlsx --spec-json '{"sheet":"Sheet1","name":"Upside","changingCells":["A2"],"values":[125]}'`
- `goal-seek execute --workbook-path /path/to/book.xlsx --spec-json '{"sheet":"Sheet1","formulaCell":"B2","targetValue":100,"changingCell":"A2"}'`
- `formula-audit export --workbook-path /path/to/book.xlsx --sheet Sheet1 --target-path /path/to/formula-audit.json`
- `automation generate --automation-type artifact-workbook --target-path build-workbook.mjs --spec-json '{"sheets":["Inputs","Dashboard"]}'`
- `graph-workbook range-set --item-id DRIVE_ITEM_ID --session-id SESSION_ID --sheet Sheet1 --range-ref A1:B2 --values-json '[[1,2]]' --dry-run`
- `fabric-semantic-model get-definition --workspace-id WORKSPACE_ID --semantic-model-id MODEL_ID --format TMDL --dry-run`
- `semantic-artifact inspect --definition-dir /path/to/tmdl`
- `dax execute --workspace-id WORKSPACE_ID --dataset-id DATASET_ID --dax-query 'EVALUATE ROW("A", 1)' --dry-run`

When passing comma-separated `--surface` values from PowerShell, quote the
value as one argument. Repeating `--surface` also works.
