=LET(
  recordId, [@[*Record ID]],
  IF(
    recordId="",
    "",
    LET(
      thisInv, ROW()-ROW(tbl_records[[#Headers],[*Record ID]]),
      supplierNumber, [@[**Supplier Number]],
      recordDateText, IF([@[*Record Date]]="", TEXT(TODAY(), "mmddyyyy"), TEXT([@[*Record Date]], "mmddyyyy")),
      relatedLineCount, COUNTIF(tbl_record_lines[*Record ID], recordId),

      parseUsableAssetByRecordId,
        LAMBDA(
          targetRecordId,
          LET(
            relatedDescriptionsLocal, IFERROR(FILTER(tbl_record_lines[Description], tbl_record_lines[*Record ID]=targetRecordId), ""),
            relatedTextRawLocal, UPPER(REGEXREPLACE(TRIM(TEXTJOIN(" ", TRUE, relatedDescriptionsLocal)), "\s+", " ")),
            relatedTextLocal, REGEXREPLACE(relatedTextRawLocal, "\s*-\s*", "-"),

            assetLabelMatchLocal,
              IFERROR(
                REGEXEXTRACT(
                  relatedTextLocal,
                  "\bASSET(?:\s*NUMBER(?:S)?)?\b\s*(?:[#:\(\)\[\]\-]\s*)*[A-Z0-9&-]{3,}\b"
                ),
                ""
              ),
            assetByLabelRawLocal,
              IFERROR(
                REGEXEXTRACT(
                  assetLabelMatchLocal,
                  "[A-Z0-9&-]{3,}$"
                ),
                ""
              ),
            assetByLabelNumericLocal,
              IF(
                OR(
                  assetByLabelRawLocal="",
                  NOT(
                    REGEXTEST(
                      assetByLabelRawLocal,
                      "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}(?:-[A-Z0-9]{1,4})?$"
                    )
                  )
                ),
                "",
                REGEXREPLACE(
                  assetByLabelRawLocal,
                  "^(?:[A-Z0-9&]{2,8}-)?(\d{7,12})(?:-[A-Z0-9]{1,4})?$",
                  "$1"
                )
              ),
            assetTagByLabelOnlyLocal,
              IF(
                OR(
                  assetByLabelRawLocal="",
                  NOT(
                    REGEXTEST(
                      assetByLabelRawLocal,
                      "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}-[A-Z0-9]{1,4}$"
                    )
                  )
                ),
                "",
                REGEXREPLACE(
                  assetByLabelRawLocal,
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
            assetByDescriptorNumericLocal,
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
            assetTagByDescriptorOnlyLocal,
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

            assetBaseCandidateLocal, IF(assetByLabelNumericLocal<>"", assetByLabelNumericLocal, assetByDescriptorNumericLocal),
            assetTagLocal, IF(assetTagByLabelOnlyLocal<>"", assetTagByLabelOnlyLocal, assetTagByDescriptorOnlyLocal),
            assetCandidateLocal, IF(assetTagLocal="", assetBaseCandidateLocal, assetBaseCandidateLocal & "-" & assetTagLocal),
            assetIsSensitiveIdentifierLocal,
              IF(
                assetCandidateLocal="",
                FALSE,
                REGEXTEST(assetBaseCandidateLocal, "^[A-HJ-NPR-Z0-9]{11,17}$")
              ),
            usableAssetLocal, IF(assetIsSensitiveIdentifierLocal, "", assetCandidateLocal),

            usableAssetLocal
          )
        ),

      usableAsset, parseUsableAssetByRecordId(recordId),

      priorRecordIds,
        IF(
          thisInv=1,
          "",
          INDEX(tbl_records[*Record ID],1):INDEX(tbl_records[*Record ID],thisInv-1)
        ),
      priorSuppliers,
        IF(
          thisInv=1,
          "",
          INDEX(tbl_records[**Supplier Number],1):INDEX(tbl_records[**Supplier Number],thisInv-1)
        ),
      priorRecordDates,
        IF(
          thisInv=1,
          "",
          INDEX(tbl_records[*Record Date],1):INDEX(tbl_records[*Record Date],thisInv-1)
        ),
      priorRecordDateTexts,
        IF(
          thisInv=1,
          "",
          IF(priorRecordDates="", TEXT(TODAY(), "mmddyyyy"), TEXT(priorRecordDates, "mmddyyyy"))
        ),
      priorRelatedLineCounts,
        IF(
          thisInv=1,
          "",
          COUNTIF(tbl_record_lines[*Record ID], priorRecordIds)
        ),
      priorUsableAssets,
        IF(
          thisInv=1,
          "",
          MAP(
            priorRecordIds,
            LAMBDA(priorRecordId, parseUsableAssetByRecordId(priorRecordId))
          )
        ),
      priorDateModeCount,
        IF(
          OR(thisInv=1, supplierNumber=""),
          0,
          SUMPRODUCT(
            --(priorSuppliers=supplierNumber),
            --(priorRecordDateTexts=recordDateText),
            --(((priorRelatedLineCounts<>1)+(priorUsableAssets=""))>0)
          )
        ),
      dateRecordNumber,
        recordDateText &
        IF(priorDateModeCount=0, "", "-" & priorDateModeCount) &
        "-TR",

      IF(
        OR(relatedLineCount<>1, usableAsset=""),
        dateRecordNumber,
        usableAsset & "-TR"
      )
    )
  )
)

