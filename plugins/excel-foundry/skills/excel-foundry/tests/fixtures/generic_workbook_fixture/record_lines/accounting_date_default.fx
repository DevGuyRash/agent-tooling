=LET(
    record_id, [@[*Record ID]],
    default_date, tbl_defaults_record_lines[Accounting Date],
    IF(record_id <> "", INDEX(default_date, 1), "")
)
