=LET(
    record_id, [@[*Record ID]],
    default_type, tbl_defaults_records[Record Type],
    IF(record_id <> "", INDEX(default_type, 1), "")
)
