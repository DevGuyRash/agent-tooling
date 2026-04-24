=LET(
  lineNums, tbl_record_lines[Line Number],
  recordsNeeded, SUM(--(lineNums&""="1")),
  thisInv, ROW()-ROW(tbl_records[[#Headers],[*Record ID]]),
  lastID, IF(
            thisInv=1,
            0,
            MAX(
              INDEX([*Record ID],1):
              INDEX([*Record ID],thisInv-1)
            )
          ),
  IF(thisInv<=recordsNeeded, lastID+1, "")
)