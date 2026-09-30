# duplicate order IDs break revenue totals

Number: 142
Reported by: you

Right now `import_rows` silently accepts duplicate order IDs and we double-count
revenue when the same row shows up twice in an export. Two things need to happen:

1. `import_rows` should raise `DuplicateOrderError` when the same order_id
   appears twice in one batch, instead of importing both.
2. The `report` command should not crash when that happens -- catch it per
   row, skip the duplicate, and add a "N duplicates skipped" line to the
   printed summary.
