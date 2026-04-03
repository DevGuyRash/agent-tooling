=LET(
  ln, [@[Line Number]],
  lnCol, tbl_invoice_lines[Line Number],
  invCol, tbl_invoice_lines[*Invoice ID],
  amtCol, tbl_invoice_lines[*Amount],
  descCol, tbl_invoice_lines[Description],
  att6Col, tbl_invoice_lines[Attribute 6],
  attCatCol, tbl_invoice_lines[Attribute Category],
  projCol, tbl_invoice_lines[Project Number],
  taskCol, tbl_invoice_lines[Task Number],
  expTypeCol, tbl_invoice_lines[Expenditure Type],
  expOrgCol, tbl_invoice_lines[Expenditure Organization],
  rowIx, ROW() - ROW(INDEX(lnCol, 1, 1)) + 1,
  IF(
    ln="",
    "",
    IF(
      rowIx=1,
      1,
      LET(
        prevIx, rowIx-1,
        prevLn, INDEX(lnCol, prevIx),
        prevInv, INDEX(invCol, prevIx),
        lnHist, TAKE(lnCol, prevIx),
        invHist, TAKE(invCol, prevIx),

        amtHist, TAKE(amtCol, prevIx),
        descHist, TAKE(descCol, prevIx),
        att6Hist, TAKE(att6Col, prevIx),
        attCatHist, TAKE(attCatCol, prevIx),
        projHist, TAKE(projCol, prevIx),
        taskHist, TAKE(taskCol, prevIx),
        expTypeHist, TAKE(expTypeCol, prevIx),
        expOrgHist, TAKE(expOrgCol, prevIx),

        blankLineMask,
          (LEN(TRIM(amtHist&""))=0) *
          (LEN(TRIM(descHist&""))=0) *
          (LEN(TRIM(att6Hist&""))=0) *
          (LEN(TRIM(attCatHist&""))=0) *
          (LEN(TRIM(projHist&""))=0) *
          (LEN(TRIM(taskHist&""))=0) *
          (LEN(TRIM(expTypeHist&""))=0) *
          (LEN(TRIM(expOrgHist&""))=0),

        incompleteInvRaw, IFERROR(FILTER(IFERROR(--invHist, 0), blankLineMask), ""),
        incompleteInv, IFERROR(FILTER(incompleteInvRaw, incompleteInvRaw>=1), ""),
        candidateInv, IFERROR(MIN(incompleteInv), ""),

        priorMaxInv, IFERROR(MAX(IFERROR(--invHist, 0)), 0),
        markerInv, priorMaxInv + 1,

        nextExpected, prevLn + 1,
        baseInv,
          IF(
            ln = nextExpected,
            prevInv,
            IF(
              ln < nextExpected,
              prevInv + 1,
              LET(
                matchIx, XMATCH(ln - 1, lnHist, 0, -1),
                hasPrevLineForInv, IFERROR(INDEX(invCol, matchIx) = prevInv, FALSE),
                IF(hasPrevLineForInv, prevInv, "ERROR")
              )
            )
          ),

        IF(
          ln=0,
          IF(candidateInv="", baseInv, candidateInv),
          baseInv
        )
      )
    )
  )
)
