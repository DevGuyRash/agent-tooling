=LET(
    record_id, [@[*Record ID]],
    default_curr, tbl_defaults_records[Record Currency],
    IF(record_id <> "", INDEX(default_curr, 1), "")
)
