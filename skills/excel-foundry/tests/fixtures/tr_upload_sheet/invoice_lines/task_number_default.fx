=LET(
    att_cat, [@[Attribute Category]],
    att_6, [@[Attribute 6]],
    proj_num, [@[Project Number]],
    default_task, tbl_defaults_invoice_lines[Task Number],
    IF(OR(att_cat<>"", att_6<>"", proj_num<>""), INDEX(default_task, 1), "")
)
