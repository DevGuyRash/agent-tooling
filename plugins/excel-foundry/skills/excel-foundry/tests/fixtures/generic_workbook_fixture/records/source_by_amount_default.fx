=LET(
    record_id, [@[*Record ID]],
    record_amt, [@[*Record Amount]],
    source_options, tbl_defaults_records[Source Options],

    IF(
        record_id <> "",
        IF(
            record_amt >= 100000,
            INDEX(source_options, 1),
            INDEX(source_options, 2)
        ),
        ""
    )
)
