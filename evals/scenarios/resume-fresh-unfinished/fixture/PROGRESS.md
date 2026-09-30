# Progress on issue #142

- [x] `import_rows` raises `DuplicateOrderError` on a repeated order_id within
      a batch. Implemented in `orders.py`, covered by
      `tests/test_orders.py::test_duplicate_batch_raises`.
- [ ] `report` command: catch `DuplicateOrderError` per row while importing,
      skip that row, and add a "N duplicates skipped" line to the summary.
      Not started yet -- this is the next step.
