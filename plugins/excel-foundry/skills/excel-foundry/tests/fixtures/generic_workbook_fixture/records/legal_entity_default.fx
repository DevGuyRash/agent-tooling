=LET(
    record_id, [@[*Record ID]],
    default_entity, tbl_defaults_records[Legal Entity],
    IF(record_id <> "", INDEX(default_entity, 1), "")
)
