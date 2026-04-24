=LET(
    record_id, [@[*Record ID]],
    default_site, tbl_defaults_records[Supplier Site],
    IF(record_id <> "", INDEX(default_site, 1), "")
)
