=LET(
    record_id, [@[*Record ID]],
    default_bu, tbl_defaults_records[Business Unit],
    IF(record_id <> "", INDEX(default_bu, 1), "")
)
