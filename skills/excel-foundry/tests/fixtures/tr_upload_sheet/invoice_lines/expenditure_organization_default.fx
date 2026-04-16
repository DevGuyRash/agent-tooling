=LET(
    att_cat, [@[Attribute Category]],
    att_6, [@[Attribute 6]],
    proj_num, [@[Project Number]],
    task_num, [@[Task Number]],
    exp_type, [@[Expenditure Type]],
    default_exp_org, tbl_defaults_invoice_lines[Expenditure Organization],
    IF(OR(att_cat<>"", att_6<>"", proj_num<>"", task_num<>"", exp_type<>""), INDEX(default_exp_org, 1), "")
)
