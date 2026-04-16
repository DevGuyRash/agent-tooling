=LET(
  lineNums, tbl_invoice_lines[Line Number],
  invoicesNeeded, SUM(--(lineNums&""="1")),
  thisInv, ROW()-ROW(tbl_invoices[[#Headers],[*Invoice ID]]),
  lastID, IF(
            thisInv=1,
            0,
            MAX(
              INDEX([*Invoice ID],1):
              INDEX([*Invoice ID],thisInv-1)
            )
          ),
  IF(thisInv<=invoicesNeeded, lastID+1, "")
)