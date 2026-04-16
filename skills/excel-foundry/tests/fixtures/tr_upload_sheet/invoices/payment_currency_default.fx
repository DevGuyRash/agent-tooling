=LET(
    invoice_id, [@[*Invoice ID]],
    default_curr, tbl_defaults_invoices[Payment Currency],
    IF(invoice_id <> "", INDEX(default_curr, 1), "")
)
