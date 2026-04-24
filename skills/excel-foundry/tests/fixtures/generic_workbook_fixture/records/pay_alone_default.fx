=LET(
    record_id, [@[*Record ID]],
    default_pay_alone, tbl_defaults_records[Pay Alone],
    IF(record_id <> "", INDEX(default_pay_alone, 1), "")
)
