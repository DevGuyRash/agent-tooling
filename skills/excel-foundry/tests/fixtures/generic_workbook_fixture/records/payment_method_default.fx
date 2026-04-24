=LET(
    record_id, [@[*Record ID]],
    default_method, tbl_defaults_records[Payment Method],
    IF(record_id <> "", INDEX(default_method, 1), "")
)
