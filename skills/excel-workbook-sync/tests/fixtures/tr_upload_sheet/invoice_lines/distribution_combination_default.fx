=LET(
  inv, [@[*Invoice ID]],
  IF(inv="","",
    LET(
      def, INDEX(tbl_defaults_invoice_lines[Distribution Combination], 1),
      ids, tbl_invoice_lines[*Invoice ID],
      dists, tbl_invoice_lines[Distribution Combination],
      thisRow, ROW()-ROW(INDEX(ids,1))+1,
      firstRow, IFERROR(XMATCH(inv, ids, 0), 0),
      IF(firstRow=0, def,
        IF(thisRow=firstRow, def,
          LET(firstDist, IFERROR(INDEX(dists, firstRow), def),
            IF(firstDist="", def, firstDist)
          )
        )
      )
    )
  )
)