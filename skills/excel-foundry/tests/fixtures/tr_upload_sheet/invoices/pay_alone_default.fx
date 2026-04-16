=LET(
    invoice_id, [@[*Invoice ID]],
    default_pay_alone, tbl_defaults_invoices[Pay Alone],
    IF(invoice_id <> "", INDEX(default_pay_alone, 1), "")
)
