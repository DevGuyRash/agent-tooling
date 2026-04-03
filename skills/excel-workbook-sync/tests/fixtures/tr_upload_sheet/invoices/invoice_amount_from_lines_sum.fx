=LET(
  note_text_1, N("Sum of nonblank line *Amount for this row's Invoice ID."),
  note_text_2, N("If ALL matching line amounts are blank, return blank so blank=blank."),
  inv_id, [@[*Invoice ID]],

  IF(
    LEN(inv_id&"")=0,
    "",
    LET(
      line_ids, tbl_invoice_lines[*Invoice ID],
      line_amts, tbl_invoice_lines[*Amount],
      has_nonblank_amt, COUNTIFS(line_ids, inv_id, line_amts, "<>")>0,
      total_amt, SUMIFS(line_amts, line_ids, inv_id, line_amts, "<>"),
      IF(has_nonblank_amt, total_amt, "")
    )
  )
)
