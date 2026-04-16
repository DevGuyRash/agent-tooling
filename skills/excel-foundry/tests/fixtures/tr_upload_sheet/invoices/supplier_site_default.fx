=LET(
    invoice_id, [@[*Invoice ID]],
    default_site, tbl_defaults_invoices[Supplier Site],
    IF(invoice_id <> "", INDEX(default_site, 1), "")
)
