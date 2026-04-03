=LET(
    att_6_check, [@[Attribute 6]],
    default_att_cat, tbl_defaults_invoice_lines[Attribute Category],
    IF(att_6_check <> "", INDEX(default_att_cat, 1), "")
)
