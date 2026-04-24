=LET(
    record_id, [@[*Record ID]],
    default_date, tbl_defaults_records[Record Received Date],
    IF(record_id <> "", INDEX(default_date, 1), "")
)
