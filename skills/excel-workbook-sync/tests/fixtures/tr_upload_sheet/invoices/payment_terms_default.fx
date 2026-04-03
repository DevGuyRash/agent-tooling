=LET(
    invoice_id, [@[*Invoice ID]],
    default_terms, tbl_defaults_invoices[Payment Terms],
    IF(invoice_id <> "", INDEX(default_terms, 1), "")
)
