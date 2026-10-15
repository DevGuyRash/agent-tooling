# Roadmap

Rough ideas, nothing here is scheduled.

- **Exports.** Finance wants the week as CSV for their spreadsheet (spec in `csv.md`). The data team wants JSON for their dashboard (spec in `json.md`), and probably Parquet or Excel after that. It would be good if exporters were pluggable, so each team could ship its own without a change to stallbook itself. No design yet.
- **Several stalls** under one data directory.
- **A `month` command** that totals a month at a time.
