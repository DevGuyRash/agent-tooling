=LET(
    invoice_id, [@[*Invoice ID]],
    default_line, tbl_defaults_invoice_lines[Line Type],
    IF(invoice_id <> "", INDEX(default_line, 1), "")
)
