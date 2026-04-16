=LET(
  invoiceId, [@[*Invoice ID]],
  IF(
    invoiceId="",
    "",
    LET(
      thisInv, ROW()-ROW(tbl_invoices[[#Headers],[*Invoice ID]]),
      supplierNumber, [@[**Supplier Number]],
      invoiceDateText, IF([@[*Invoice Date]]="", TEXT(TODAY(), "mmddyyyy"), TEXT([@[*Invoice Date]], "mmddyyyy")),
      relatedLineCount, COUNTIF(tbl_invoice_lines[*Invoice ID], invoiceId),

      parseUsableStockByInvoiceId,
        LAMBDA(
          targetInvoiceId,
          LET(
            relatedDescriptionsLocal, IFERROR(FILTER(tbl_invoice_lines[Description], tbl_invoice_lines[*Invoice ID]=targetInvoiceId), ""),
            relatedTextRawLocal, UPPER(REGEXREPLACE(TRIM(TEXTJOIN(" ", TRUE, relatedDescriptionsLocal)), "\s+", " ")),
            relatedTextLocal, REGEXREPLACE(relatedTextRawLocal, "\s*-\s*", "-"),

            stockLabelMatchLocal,
              IFERROR(
                REGEXEXTRACT(
                  relatedTextLocal,
                  "\bSTOCK(?:\s*NUMBER(?:S)?)?\b\s*(?:[#:\(\)\[\]\-]\s*)*[A-Z0-9&-]{3,}\b"
                ),
                ""
              ),
            stockByLabelRawLocal,
              IFERROR(
                REGEXEXTRACT(
                  stockLabelMatchLocal,
                  "[A-Z0-9&-]{3,}$"
                ),
                ""
              ),
            stockByLabelNumericLocal,
              IF(
                OR(
                  stockByLabelRawLocal="",
                  NOT(
                    REGEXTEST(
                      stockByLabelRawLocal,
                      "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}(?:-[A-Z0-9]{1,4})?$"
                    )
                  )
                ),
                "",
                REGEXREPLACE(
                  stockByLabelRawLocal,
                  "^(?:[A-Z0-9&]{2,8}-)?(\d{7,12})(?:-[A-Z0-9]{1,4})?$",
                  "$1"
                )
              ),
            stockTagByLabelOnlyLocal,
              IF(
                OR(
                  stockByLabelRawLocal="",
                  NOT(
                    REGEXTEST(
                      stockByLabelRawLocal,
                      "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}-[A-Z0-9]{1,4}$"
                    )
                  )
                ),
                "",
                REGEXREPLACE(
                  stockByLabelRawLocal,
                  "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}-([A-Z0-9]{1,4})$",
                  "$1"
                )
              ),

            descriptorMatchRawLocal,
              IFERROR(
                REGEXEXTRACT(
                  relatedTextLocal,
                  "(?:^|[^A-Z0-9&])(?:[A-Z0-9&]{2,8}-)?\d{7,12}(?:-[A-Z0-9]{1,4})?-[A-HJ-NPR-Z0-9]{11,17}(?:-\d{3,})?(?:-[A-Z0-9&]{2,30})*(?:$|[^A-Z0-9&])"
                ),
                ""
              ),
            descriptorMatchLocal, REGEXREPLACE(descriptorMatchRawLocal, "^[^A-Z0-9&]+|[^A-Z0-9&]+$", ""),
            stockByDescriptorNumericLocal,
              IF(
                OR(
                  descriptorMatchLocal="",
                  NOT(
                    REGEXTEST(
                      descriptorMatchLocal,
                      "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}(?:-[A-Z0-9]{1,4})?-[A-HJ-NPR-Z0-9]{11,17}(?:-\d{3,})?(?:-[A-Z0-9&]{2,30})*$"
                    )
                  )
                ),
                "",
                REGEXREPLACE(
                  descriptorMatchLocal,
                  "^(?:[A-Z0-9&]{2,8}-)?(\d{7,12})(?:-[A-Z0-9]{1,4})?-[A-HJ-NPR-Z0-9]{11,17}(?:-\d{3,})?(?:-[A-Z0-9&]{2,30})*$",
                  "$1"
                )
              ),
            stockTagByDescriptorOnlyLocal,
              IF(
                OR(
                  descriptorMatchLocal="",
                  NOT(
                    REGEXTEST(
                      descriptorMatchLocal,
                      "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}-[A-Z0-9]{1,4}-[A-HJ-NPR-Z0-9]{11,17}(?:-\d{3,})?(?:-[A-Z0-9&]{2,30})*$"
                    )
                  )
                ),
                "",
                REGEXREPLACE(
                  descriptorMatchLocal,
                  "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}-([A-Z0-9]{1,4})-[A-HJ-NPR-Z0-9]{11,17}(?:-\d{3,})?(?:-[A-Z0-9&]{2,30})*$",
                  "$1"
                )
              ),

            stockBaseCandidateLocal, IF(stockByLabelNumericLocal<>"", stockByLabelNumericLocal, stockByDescriptorNumericLocal),
            stockTagLocal, IF(stockTagByLabelOnlyLocal<>"", stockTagByLabelOnlyLocal, stockTagByDescriptorOnlyLocal),
            stockCandidateLocal, IF(stockTagLocal="", stockBaseCandidateLocal, stockBaseCandidateLocal & "-" & stockTagLocal),
            stockIsVinLikeLocal,
              IF(
                stockCandidateLocal="",
                FALSE,
                REGEXTEST(stockBaseCandidateLocal, "^[A-HJ-NPR-Z0-9]{11,17}$")
              ),
            usableStockLocal, IF(stockIsVinLikeLocal, "", stockCandidateLocal),

            usableStockLocal
          )
        ),

      usableStock, parseUsableStockByInvoiceId(invoiceId),

      priorInvoiceIds,
        IF(
          thisInv=1,
          "",
          INDEX(tbl_invoices[*Invoice ID],1):INDEX(tbl_invoices[*Invoice ID],thisInv-1)
        ),
      priorSuppliers,
        IF(
          thisInv=1,
          "",
          INDEX(tbl_invoices[**Supplier Number],1):INDEX(tbl_invoices[**Supplier Number],thisInv-1)
        ),
      priorInvoiceDates,
        IF(
          thisInv=1,
          "",
          INDEX(tbl_invoices[*Invoice Date],1):INDEX(tbl_invoices[*Invoice Date],thisInv-1)
        ),
      priorInvoiceDateTexts,
        IF(
          thisInv=1,
          "",
          IF(priorInvoiceDates="", TEXT(TODAY(), "mmddyyyy"), TEXT(priorInvoiceDates, "mmddyyyy"))
        ),
      priorRelatedLineCounts,
        IF(
          thisInv=1,
          "",
          COUNTIF(tbl_invoice_lines[*Invoice ID], priorInvoiceIds)
        ),
      priorUsableStocks,
        IF(
          thisInv=1,
          "",
          MAP(
            priorInvoiceIds,
            LAMBDA(priorInvoiceId, parseUsableStockByInvoiceId(priorInvoiceId))
          )
        ),
      priorDateModeCount,
        IF(
          OR(thisInv=1, supplierNumber=""),
          0,
          SUMPRODUCT(
            --(priorSuppliers=supplierNumber),
            --(priorInvoiceDateTexts=invoiceDateText),
            --(((priorRelatedLineCounts<>1)+(priorUsableStocks=""))>0)
          )
        ),
      dateInvoiceNumber,
        invoiceDateText &
        IF(priorDateModeCount=0, "", "-" & priorDateModeCount) &
        "-TR",

      IF(
        OR(relatedLineCount<>1, usableStock=""),
        dateInvoiceNumber,
        usableStock & "-TR"
      )
    )
  )
)
