=LET(
  invID, [@[*Invoice ID]],
  IF(
    invID="",
    "",
    LET(
      ids, tbl_invoice_lines[*Invoice ID],
      hasMatch, COUNTIF(ids, invID)>0,
      IF(
        NOT(hasMatch),
        "",
        IFERROR(
          LET(
            txtCol, IF(tbl_invoice_lines[Item Description]<>"",
                       tbl_invoice_lines[Item Description],
                       tbl_invoice_lines[Description]
                   ),

            first, XMATCH(invID, ids, 0),

            firstTxt, LET(
              t, TRIM("" & INDEX(txtCol, first)),
              IF(OR(t="", t="0"), "", t)
            ),

            nextSame, IFERROR(INDEX(ids, first+1)=invID, FALSE),

            IF(
              NOT(nextSame),
              firstTxt,
              LET(
                tailIDs, DROP(ids, first-1),
                tailTxt, DROP(txtCol, first-1),

                endRel, IFERROR(XMATCH(TRUE, tailIDs<>invID, 0), ROWS(tailIDs)+1),
                grpTxt, TAKE(tailTxt, endRel-1),

                grpTxtT, TRIM("" & grpTxt),
                hasAny, OR((grpTxtT<>"")*(grpTxtT<>"0")),

                IF(
                  NOT(hasAny),
                  "",
                  LET(
                    hyTxt, IFERROR(XLOOKUP(TRUE, ISNUMBER(SEARCH("-", grpTxtT)), grpTxtT, ""), ""),
                    prefix, IFERROR(TEXTBEFORE(hyTxt, "-"), ""),
                    IF(prefix<>"", prefix&"-Titles", "Titles")
                  )
                )
              )
            )
          ),
          ""
        )
      )
    )
  )
)
