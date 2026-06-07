=LET(
    record_id, [@[*Record ID]],
    default_line, tbl_defaults_record_lines[Line Type],
    IF(record_id <> "", INDEX(default_line, 1), "")
)
