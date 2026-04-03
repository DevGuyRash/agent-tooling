=LET(
    invoice_id, [@[*Invoice ID]],
    default_type, tbl_defaults_invoices[Invoice Type],
    IF(invoice_id <> "", INDEX(default_type, 1), "")
)
