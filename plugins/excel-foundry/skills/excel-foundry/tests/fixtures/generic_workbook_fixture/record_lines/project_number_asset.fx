=LET(
  d, TRIM("" & [@Description]),
  IF(
    d="",
    "",
    LET(
      normalizedText, UPPER(REGEXREPLACE(d, "\s+", " ")),
      canonicalText, REGEXREPLACE(normalizedText, "\s*-\s*", "-"),
      assetLabelMatch,
        IFERROR(
          REGEXEXTRACT(
            canonicalText,
            "\bASSET(?:\s*NUMBER(?:S)?)?\b\s*(?:[#:\(\)\[\]\-]\s*)*[A-Z0-9&-]{3,}\b"
          ),
          ""
        ),
      assetByLabelRaw,
        IFERROR(
          REGEXEXTRACT(
            assetLabelMatch,
            "[A-Z0-9&-]{3,}$"
          ),
          ""
        ),
      assetByLabel,
        IF(
          assetByLabelRaw="",
          "",
          IFERROR(
            REGEXEXTRACT(
              assetByLabelRaw,
              "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}"
            ),
            ""
          )
        ),
      assetByLabelNumeric,
        IF(
          assetByLabel="",
          "",
          REGEXREPLACE(assetByLabel, "^[A-Z0-9&]{2,8}-", "")
        ),
      descriptorMatchRaw,
        IFERROR(
          REGEXEXTRACT(
            canonicalText,
            "(?:^|[^A-Z0-9&])(?:[A-Z0-9&]{2,8}-)?\d{7,12}(?:-[A-Z0-9]{1,4})?-[A-HJ-NPR-Z0-9]{11,17}(?:-\d{3,})?(?:-[A-Z0-9&]{2,30})*(?:$|[^A-Z0-9&])"
          ),
          ""
        ),
      descriptorMatch, REGEXREPLACE(descriptorMatchRaw, "^[^A-Z0-9&]+|[^A-Z0-9&]+$", ""),
      assetByDescriptor,
        IFERROR(
          REGEXEXTRACT(
            descriptorMatch,
            "^(?:[A-Z0-9&]{2,8}-)?\d{7,12}"
          ),
          ""
        ),
      assetByDescriptorNumeric,
        IF(
          assetByDescriptor="",
          "",
          REGEXREPLACE(assetByDescriptor, "^[A-Z0-9&]{2,8}-", "")
        ),
      assetCandidate, IF(assetByLabelNumeric<>"", assetByLabelNumeric, assetByDescriptorNumeric),
      assetIsSensitiveIdentifier,
        IF(
          assetCandidate="",
          FALSE,
          REGEXTEST(assetCandidate, "^[A-HJ-NPR-Z0-9]{11,17}$")
        ),
      IF(assetIsSensitiveIdentifier, "", assetCandidate)
    )
  )
)

