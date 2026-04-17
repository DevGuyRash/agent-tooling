# Query

`inspect` returns a compact workbook summary.

`query` returns detailed JSON for selected surfaces.

Direct workbook commands use the same launcher for narrow operations:

- `workbook inspect|capabilities|create|diff`
- `workbook save-as|convert|repair|compatibility|document-inspect`
- `workbook links|break-links|repoint-links|safe-export`
- `manifest validate|doctor|migrate`
- `sheet list|create`
- `name list|set|delete`
- `table list|read`
- `query list`
- `cell get|set`
- `range get|set`

Advanced direct workbook commands use Excel COM on Windows:

- `table get|create|update|delete`
- `query get|set|delete|refresh`
- `connection list|get`
- `chart list|get`
- `pivot list|get`

`plan` returns per-surface capability, compare, merge, and intended write
counts before mutation.

`compare` returns per-surface `strict`, `normalized`, and `intent` results for
repo artifacts versus the current workbook.

`sync` is the plan-centric manifest execution command. It is dry-run by
default and requires `--apply` to mutate supported package-backed surfaces.

Common flags:

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
- `--address`
- `--range-ref`
- `--value-json`
- `--values-json`
- `--spec-json`
- `--spec-file`
- `--refers-to`

Default output is JSON. Use `inspect` for counts and capability summary. Use
`query` for artifact-level detail that can later be written into sync artifacts.
Use `plan` before mutating a manifest workspace when you need backend and
surface writeability decisions first. Use `compare` when you need per-surface
artifact drift instead of one coarse workbook result.
- `workbook save-as --workbook-path /path/to/book.xlsm --target-path /path/to/book.xlsb`
- `workbook convert --workbook-path /path/to/book.xlsx --target-format csv`
- `workbook repair --workbook-path /path/to/damaged.xlsx --mode repair --target-path /path/to/damaged.repaired.xlsx`
- `workbook compatibility --workbook-path /path/to/book.xlsm --target-format ods`
- `workbook document-inspect --workbook-path /path/to/book.xlsx`
- `workbook links --workbook-path /path/to/book.xlsx`
- `workbook break-links --workbook-path /path/to/book.xlsx --spec-json '{"all":true}'`
- `workbook repoint-links --workbook-path /path/to/book.xlsx --spec-file /path/to/link-map.json`
- `workbook safe-export --workbook-path /path/to/book.xlsx --target-path /path/to/book.share-safe.xlsx`

When you pass a comma-separated `--surface` value from PowerShell, quote it as one argument. Repeating `--surface` also works.
