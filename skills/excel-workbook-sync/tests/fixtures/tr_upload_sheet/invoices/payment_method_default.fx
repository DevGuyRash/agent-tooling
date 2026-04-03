=LET(
    invoice_id, [@[*Invoice ID]],
    default_method, tbl_defaults_invoices[Payment Method],
    IF(invoice_id <> "", INDEX(default_method, 1), "")
)
