=LET(
  d, TRIM("" & [@Description]),
  IF(
    d="",
    "",
    LET(
      normalizedText, UPPER(REGEXREPLACE(d, "\s+", " ")),
      canonicalText, REGEXREPLACE(normalizedText, "\s*-\s*", "-"),
      pidLabelMatch,
        IFERROR(
          REGEXEXTRACT(
            canonicalText,
            "\bPID(?:\s*NUMBER(?:S)?)?\b\s*(?:[#:\(\)\[\]\-]\s*)*\d{3,}\b"
          ),
          ""
        ),
      pidByLabel,
        IF(
          pidLabelMatch="",
          "",
          IFERROR(
            REGEXEXTRACT(
              pidLabelMatch,
              "\d{3,}$"
            ),
            ""
          )
        ),
      pidByDescriptor,
        IF(
          pidByLabel<>"",
          "",
          LET(
            pidByDescriptorRaw,
              IFERROR(
                REGEXEXTRACT(
                  canonicalText,
                  "(?:^|[^A-Z0-9&])(?:[A-Z0-9&]{2,8}-)?\d{7,12}(?:-[A-Z0-9]{1,4})?-[A-HJ-NPR-Z0-9]{11,17}-(\d{3,})(?:-[A-Z0-9&]{2,30})*(?:$|[^A-Z0-9&])"
                ),
                ""
              ),
            pidDescriptorText,
              IF(
                pidByDescriptorRaw="",
                "",
                REGEXREPLACE(pidByDescriptorRaw, "^[^A-Z0-9&]+|[^A-Z0-9&]+$", "")
              ),
            pidAfterSensitiveId,
              IF(
                pidDescriptorText="",
                "",
                REGEXREPLACE(pidDescriptorText, "^.*-[A-HJ-NPR-Z0-9]{11,17}-", "")
              ),
            IF(
              pidByDescriptorRaw="",
              "",
              IF(
                REGEXTEST(pidByDescriptorRaw, "^\d{3,}$"),
                pidByDescriptorRaw,
                IFERROR(
                  REGEXEXTRACT(
                    pidAfterSensitiveId,
                    "^\d{3,}"
                  ),
                  ""
                )
              )
            )
          )
        ),
      IF(pidByLabel<>"", pidByLabel, pidByDescriptor)
    )
  )
)

