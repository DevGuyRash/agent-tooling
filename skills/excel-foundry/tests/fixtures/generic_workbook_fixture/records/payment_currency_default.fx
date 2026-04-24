=LET(
    record_id, [@[*Record ID]],
    default_curr, tbl_defaults_records[Payment Currency],
    IF(record_id <> "", INDEX(default_curr, 1), "")
)
