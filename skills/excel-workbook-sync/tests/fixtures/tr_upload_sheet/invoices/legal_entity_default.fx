=LET(
    invoice_id, [@[*Invoice ID]],
    default_entity, tbl_defaults_invoices[Legal Entity],
    IF(invoice_id <> "", INDEX(default_entity, 1), "")
)
