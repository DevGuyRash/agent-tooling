=LET(
    invoice_id, [@[*Invoice ID]],
    default_date, tbl_defaults_invoices[Invoice Date],
    IF(invoice_id <> "", INDEX(default_date, 1), "")
)
