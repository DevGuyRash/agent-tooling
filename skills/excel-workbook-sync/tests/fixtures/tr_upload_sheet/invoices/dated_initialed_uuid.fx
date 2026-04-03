=LET(
  initials, "AK",
  dateText, TEXT(TODAY(), "mmddyyyy"),
  saltValue, "AB132J",
  saltRounds, 3,
  partsRequested, 4,

  fileInfo, CELL("filename", $A$1),

  idText,
    IF(fileInfo="","",
      LET(
        openBracketPos, FIND("[", fileInfo),
        closeBracketPos, FIND("]", fileInfo, openBracketPos),
        sourceText, LEFT(fileInfo, closeBracketPos),

        roundCount, MAX(0, IFERROR(INT(saltRounds), 0)),
        partCount, MAX(0, IFERROR(INT(partsRequested), 0)),
        saltText, "" & saltValue,

        chunkBase, 2^16,
        modulusWord, chunkBase^2,
        fnvPrime, 16777619,

        mulMod, LAMBDA(leftNum, rightNum,
          LET(
            leftLow, MOD(leftNum, chunkBase),
            leftHigh, INT(leftNum/chunkBase),
            rightLow, MOD(rightNum, chunkBase),
            rightHigh, INT(rightNum/chunkBase),
            MOD(
              leftLow*rightLow + MOD(leftLow*rightHigh + leftHigh*rightLow, chunkBase)*chunkBase,
              modulusWord
            )
          )
        ),

        fnvHash, LAMBDA(textIn,
          REDUCE(2166136261, SEQUENCE(LEN(textIn)), LAMBDA(hashVal, indexPos,
            mulMod(BITXOR(hashVal, UNICODE(MID(textIn, indexPos, 1))), fnvPrime)
          ))
        ),

        partHex, LAMBDA(partIndex,
          LET(
            partLabel, "P"&partIndex,
            initHash, fnvHash(sourceText & "|" & saltText & "|" & partLabel),
            finalHash,
              IF(roundCount<1,
                initHash,
                REDUCE(
                  initHash,
                  SEQUENCE(roundCount),
                  LAMBDA(h, step,
                    fnvHash(BASE(h, 16, 8) & "|" & saltText & "|" & partLabel & "|" & step)
                  )
                )
              ),
            LOWER(BASE(finalHash, 16, 8))
          )
        ),

        IF(partCount<1,
          "",
          REDUCE(
            "",
            SEQUENCE(partCount),
            LAMBDA(acc, idx,
              acc & IF(acc="","","-") & partHex(idx)
            )
          )
        )
      )
    ),

  finalText, dateText & initials & "-TR" & IF(idText="","","-" & idText),
  finalText
)
