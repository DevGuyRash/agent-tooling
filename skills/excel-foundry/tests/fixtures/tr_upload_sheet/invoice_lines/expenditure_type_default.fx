=LET(
    att_cat, [@[Attribute Category]],
    att_6, [@[Attribute 6]],
    proj_num, [@[Project Number]],
    default_exp_type, tbl_defaults_invoice_lines[Expenditure Type],
    IF(OR(att_cat<>"", att_6<>"", proj_num<>""), INDEX(default_exp_type, 1), "")
)
