=LET(
    invoice_id, [@[*Invoice ID]],
    default_bu, tbl_defaults_invoices[Business Unit],
    IF(invoice_id <> "", INDEX(default_bu, 1), "")
)
