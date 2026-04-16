=LET(
    invoice_id, [@[*Invoice ID]],
    default_date, tbl_defaults_invoice_lines[Accounting Date],
    IF(invoice_id <> "", INDEX(default_date, 1), "")
)
