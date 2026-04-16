=LET(
    invoice_id, [@[*Invoice ID]],
    invoice_amt, [@[*Invoice Amount]],
    source_options, tbl_defaults_invoices[Source Options],

    IF(
        invoice_id <> "",
        IF(
            invoice_amt >= 100000,
            INDEX(source_options, 1),
            INDEX(source_options, 2)
        ),
        ""
    )
)
