# Query

`inspect` returns a compact workbook summary.

`query` returns detailed JSON for selected surfaces.

Common flags:

- `--workbook-path`
- `--manifest-path`
- `--surface tables,names,cf,vba,project,references`

Default output is JSON. Use `inspect` for counts and capability summary. Use
`query` for artifact-level detail that can later be written into sync artifacts.
