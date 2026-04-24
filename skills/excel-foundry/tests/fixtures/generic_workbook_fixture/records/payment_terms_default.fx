=LET(
    record_id, [@[*Record ID]],
    default_terms, tbl_defaults_records[Payment Terms],
    IF(record_id <> "", INDEX(default_terms, 1), "")
)
