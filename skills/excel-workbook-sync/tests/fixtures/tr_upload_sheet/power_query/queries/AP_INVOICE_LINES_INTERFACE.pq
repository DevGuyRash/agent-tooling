let
    Source = Excel.Workbook(File.Contents("C:\Users\E135328\Documents\Templates\Base\T&R UPLOAD TEMPLATE.xlsm"), null, true),
    AP_INVOICE_LINES_INTERFACE_Sheet = Source{[Item="AP_INVOICE_LINES_INTERFACE",Kind="Sheet"]}[Data],
    #"Removed Top Rows" = Table.Skip(AP_INVOICE_LINES_INTERFACE_Sheet,3),
    #"Promoted Headers" = Table.PromoteHeaders(#"Removed Top Rows", [PromoteAllScalars=true]),
    #"Added Index" = Table.AddIndexColumn(#"Promoted Headers", "Index", 0, 1, Int64.Type),
    #"Cpy *Invoice Amount > *Amount" = /* ==============================================================
   ROBUST TEMPLATE: Fill/overwrite from ANOTHER query via flat join
   --------------------------------------------------------------
   WHAT THIS DOES
   - Left (ThisTable): your current query step.
   - Right (OtherQuery): some other query (its *name*; evaluates to its final step).
   - Joins on KeysThis ↔ KeysOther (1 or many columns).
   - Copies the right-side SourceColOther into the left-side TargetColThis.
   - Collision-safe: renames right-side key columns to avoid duplicate names.
   - Safe checks: verifies the right-side source column exists pre-join,
     then auto-detects what its name becomes after the join.
   - “Fill only when null/blank” or “overwrite all” toggle.

   HOW TO USE
   1) Edit the CONFIG block only (names are case-sensitive).
   2) If your keys are numbers on one side and text on the other, set KeyTypes*.
   3) If you still see unexpected nulls, check key values & types in both queries.

   COMMON GOTCHAS
   - Column names must match exactly (spaces, punctuation, hidden trailing spaces).
   - Data types on the join keys must be compatible (text ↔ text, number ↔ number).
   - If SourceColOther is itself a join key, it will land with the "__rK_" prefix.
   ============================================================== */

let
  // =========================
  // ========= CONFIG ========
  // =========================
  ThisTable         = #"Added Index",   // your current step/table
  OtherQuery        = #"AP_INVOICES_INTERFACE",                          // the other query (its NAME)
  KeysThis          = {"Index"},                           // key(s) in ThisTable (order matters)
  KeysOther         = {"Index"},                           // corresponding key(s) in OtherQuery (same order/length)
  TargetColThis     = "*Amount",                   // column to fill/overwrite in ThisTable
  SourceColOther    = "*Invoice Amount",                   // column to copy from in OtherQuery
  ReplaceNullsOnly  = true,                                // true = fill only blanks; false = overwrite all
  FromOtherNameBase = "__FromOther",                       // temp name for right-side source (if it isn't a key)

  // OPTIONAL: align key types *before* the join (uncomment & set if needed)
  // Example: if both sides use Int64 indices:
  // KeyTypesThis      = {Int64.Type},
  // KeyTypesOther     = {Int64.Type},

  // ===============================
  // ===== IMPLEMENTATION (no edits)
  // ===============================

  // 0) Left-side names and temp name that won’t collide
  LeftNames       = Table.ColumnNames(ThisTable),
  FromOtherName   = if List.Contains(LeftNames, FromOtherNameBase)
                    then FromOtherNameBase & "_r" else FromOtherNameBase,

  // 1) Right side: keep only keys + the source column we want
  //    MissingField.Ignore prevents hard errors if you typo a name—but we’ll validate next.
  OtherSlim0      = Table.SelectColumns(OtherQuery, List.Distinct(KeysOther & {SourceColOther}), MissingField.Ignore),

  // 1a) Guardrail: ensure the right-side *SourceColOther* actually exists pre-join.
  RightHasSource  = List.Contains(Table.ColumnNames(OtherSlim0), SourceColOther),
  _CheckSource    = if not RightHasSource then
                      error Error.Record(
                        "MissingSourceColumn",
                        "Right-side column '" & SourceColOther & "' was not found in the other query.",
                        [ RightColumns = Table.ColumnNames(OtherQuery) ]
                      )
                    else null,

  // 2) (Optional) align key types; uncomment CONFIG above if you need it.
  // ThisTableFixed  = if (try List.Count(KeyTypesThis) otherwise 0) = List.Count(KeysThis)
  //                   then Table.TransformColumnTypes(ThisTable, List.Zip({KeysThis, KeyTypesThis}))
  //                   else ThisTable,
  // OtherSlimFixed  = if (try List.Count(KeyTypesOther) otherwise 0) = List.Count(KeysOther)
  //                   then Table.TransformColumnTypes(OtherSlim0, List.Zip({KeysOther, KeyTypesOther}))
  //                   else OtherSlim0,

  // If you didn’t set KeyTypes*, we just pass through:
  ThisTableFixed  = ThisTable,
  OtherSlimFixed  = OtherSlim0,

  // 3) Collision-safe: rename right-side *key* columns so they won’t duplicate left names
  //    e.g., Index → __rK_Index (we’ll join using these renamed keys)
  KeyRenamePairs  = List.Transform(KeysOther, each {_, "__rK_" & _}),
  OtherKeysRenamed= Table.RenameColumns(OtherSlimFixed, KeyRenamePairs, MissingField.Ignore),
  KeysOtherRenamed= List.Transform(KeysOther, each "__rK_" & _),

  // 4) If the source column is NOT one of the keys, rename it to a known temp name
  OtherPrepared   = if List.Contains(KeysOther, SourceColOther)
                    then OtherKeysRenamed
                    else Table.RenameColumns(OtherKeysRenamed, {{SourceColOther, FromOtherName}}, MissingField.Ignore),

  // 5) Flat join (no nested tables) on left keys ↔ right renamed keys
  Joined0         = Table.Join(ThisTableFixed, KeysThis, OtherPrepared, KeysOtherRenamed, JoinKind.LeftOuter),

  // 6) Figure out what the source column is *called after the join*.
  //    It could be:
  //      - FromOtherName     (if we renamed a non-key source)
  //      - "__rK_" & SourceColOther (if the source is also a key)
  //      - SourceColOther    (if neither rename applied)
  RightNamesAfter = Table.ColumnNames(Joined0),
  Candidates      = { FromOtherName, "__rK_" & SourceColOther, SourceColOther },
  SourceAfterJoin =
      let hits = List.Select(Candidates, each List.Contains(RightNamesAfter, _))
      in  if List.Count(hits) > 0
          then hits{0}
          else error Error.Record(
                 "JoinedSourceMissing",
                 "After join, the source column was not found. Checked names: " & Text.Combine(Candidates, ", "),
                 [ JoinedColumns = RightNamesAfter,
                   RightColumnsPreJoin = Table.ColumnNames(OtherPrepared) ]
               ),

  // 7) Ensure the left target column exists (so ReplaceValue won’t fail)
  Joined          = if List.Contains(RightNamesAfter, TargetColThis)
                    then Joined0
                    else Table.AddColumn(Joined0, TargetColThis, each null),

  // 8) Fill/overwrite the target from the joined source
  Replaced        = if ReplaceNullsOnly
                    then Table.ReplaceValue(Joined, null, each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis})
                    else Table.ReplaceValue(Joined, each Record.Field(_, TargetColThis), each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis}),

  // 9) Clean up: drop the right-side renamed key columns and the temp source column
  DropCols        = List.Distinct(KeysOtherRenamed & {SourceAfterJoin}),
  Clean           = Table.RemoveColumns(Replaced, DropCols)
in
  Clean,
    #"Cpy Description -> Description" = /* ==============================================================
   ROBUST TEMPLATE: Fill/overwrite from ANOTHER query via flat join
   --------------------------------------------------------------
   WHAT THIS DOES
   - Left (ThisTable): your current query step.
   - Right (OtherQuery): some other query (its *name*; evaluates to its final step).
   - Joins on KeysThis ↔ KeysOther (1 or many columns).
   - Copies the right-side SourceColOther into the left-side TargetColThis.
   - Collision-safe: renames right-side key columns to avoid duplicate names.
   - Safe checks: verifies the right-side source column exists pre-join,
     then auto-detects what its name becomes after the join.
   - “Fill only when null/blank” or “overwrite all” toggle.

   HOW TO USE
   1) Edit the CONFIG block only (names are case-sensitive).
   2) If your keys are numbers on one side and text on the other, set KeyTypes*.
   3) If you still see unexpected nulls, check key values & types in both queries.

   COMMON GOTCHAS
   - Column names must match exactly (spaces, punctuation, hidden trailing spaces).
   - Data types on the join keys must be compatible (text ↔ text, number ↔ number).
   - If SourceColOther is itself a join key, it will land with the "__rK_" prefix.
   ============================================================== */

let
  // =========================
  // ========= CONFIG ========
  // =========================
  ThisTable         = #"Cpy *Invoice Amount > *Amount",   // your current step/table
  OtherQuery        = #"AP_INVOICES_INTERFACE",                          // the other query (its NAME)
  KeysThis          = {"Index"},                           // key(s) in ThisTable (order matters)
  KeysOther         = {"Index"},                           // corresponding key(s) in OtherQuery (same order/length)
  TargetColThis     = "Description",                   // column to fill/overwrite in ThisTable
  SourceColOther    = "Description",                   // column to copy from in OtherQuery
  ReplaceNullsOnly  = true,                                // true = fill only blanks; false = overwrite all
  FromOtherNameBase = "__FromOther",                       // temp name for right-side source (if it isn't a key)

  // OPTIONAL: align key types *before* the join (uncomment & set if needed)
  // Example: if both sides use Int64 indices:
  // KeyTypesThis      = {Int64.Type},
  // KeyTypesOther     = {Int64.Type},

  // ===============================
  // ===== IMPLEMENTATION (no edits)
  // ===============================

  // 0) Left-side names and temp name that won’t collide
  LeftNames       = Table.ColumnNames(ThisTable),
  FromOtherName   = if List.Contains(LeftNames, FromOtherNameBase)
                    then FromOtherNameBase & "_r" else FromOtherNameBase,

  // 1) Right side: keep only keys + the source column we want
  //    MissingField.Ignore prevents hard errors if you typo a name—but we’ll validate next.
  OtherSlim0      = Table.SelectColumns(OtherQuery, List.Distinct(KeysOther & {SourceColOther}), MissingField.Ignore),

  // 1a) Guardrail: ensure the right-side *SourceColOther* actually exists pre-join.
  RightHasSource  = List.Contains(Table.ColumnNames(OtherSlim0), SourceColOther),
  _CheckSource    = if not RightHasSource then
                      error Error.Record(
                        "MissingSourceColumn",
                        "Right-side column '" & SourceColOther & "' was not found in the other query.",
                        [ RightColumns = Table.ColumnNames(OtherQuery) ]
                      )
                    else null,

  // 2) (Optional) align key types; uncomment CONFIG above if you need it.
  // ThisTableFixed  = if (try List.Count(KeyTypesThis) otherwise 0) = List.Count(KeysThis)
  //                   then Table.TransformColumnTypes(ThisTable, List.Zip({KeysThis, KeyTypesThis}))
  //                   else ThisTable,
  // OtherSlimFixed  = if (try List.Count(KeyTypesOther) otherwise 0) = List.Count(KeysOther)
  //                   then Table.TransformColumnTypes(OtherSlim0, List.Zip({KeysOther, KeyTypesOther}))
  //                   else OtherSlim0,

  // If you didn’t set KeyTypes*, we just pass through:
  ThisTableFixed  = ThisTable,
  OtherSlimFixed  = OtherSlim0,

  // 3) Collision-safe: rename right-side *key* columns so they won’t duplicate left names
  //    e.g., Index → __rK_Index (we’ll join using these renamed keys)
  KeyRenamePairs  = List.Transform(KeysOther, each {_, "__rK_" & _}),
  OtherKeysRenamed= Table.RenameColumns(OtherSlimFixed, KeyRenamePairs, MissingField.Ignore),
  KeysOtherRenamed= List.Transform(KeysOther, each "__rK_" & _),

  // 4) If the source column is NOT one of the keys, rename it to a known temp name
  OtherPrepared   = if List.Contains(KeysOther, SourceColOther)
                    then OtherKeysRenamed
                    else Table.RenameColumns(OtherKeysRenamed, {{SourceColOther, FromOtherName}}, MissingField.Ignore),

  // 5) Flat join (no nested tables) on left keys ↔ right renamed keys
  Joined0         = Table.Join(ThisTableFixed, KeysThis, OtherPrepared, KeysOtherRenamed, JoinKind.LeftOuter),

  // 6) Figure out what the source column is *called after the join*.
  //    It could be:
  //      - FromOtherName     (if we renamed a non-key source)
  //      - "__rK_" & SourceColOther (if the source is also a key)
  //      - SourceColOther    (if neither rename applied)
  RightNamesAfter = Table.ColumnNames(Joined0),
  Candidates      = { FromOtherName, "__rK_" & SourceColOther, SourceColOther },
  SourceAfterJoin =
      let hits = List.Select(Candidates, each List.Contains(RightNamesAfter, _))
      in  if List.Count(hits) > 0
          then hits{0}
          else error Error.Record(
                 "JoinedSourceMissing",
                 "After join, the source column was not found. Checked names: " & Text.Combine(Candidates, ", "),
                 [ JoinedColumns = RightNamesAfter,
                   RightColumnsPreJoin = Table.ColumnNames(OtherPrepared) ]
               ),

  // 7) Ensure the left target column exists (so ReplaceValue won’t fail)
  Joined          = if List.Contains(RightNamesAfter, TargetColThis)
                    then Joined0
                    else Table.AddColumn(Joined0, TargetColThis, each null),

  // 8) Fill/overwrite the target from the joined source
  Replaced        = if ReplaceNullsOnly
                    then Table.ReplaceValue(Joined, null, each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis})
                    else Table.ReplaceValue(Joined, each Record.Field(_, TargetColThis), each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis}),

  // 9) Clean up: drop the right-side renamed key columns and the temp source column
  DropCols        = List.Distinct(KeysOtherRenamed & {SourceAfterJoin}),
  Clean           = Table.RemoveColumns(Replaced, DropCols)
in
  Clean,
    #"Cpy Description -> Item Description" = /* ==============================================================
   ROBUST TEMPLATE: Fill/overwrite from ANOTHER query via flat join
   --------------------------------------------------------------
   WHAT THIS DOES
   - Left (ThisTable): your current query step.
   - Right (OtherQuery): some other query (its *name*; evaluates to its final step).
   - Joins on KeysThis ↔ KeysOther (1 or many columns).
   - Copies the right-side SourceColOther into the left-side TargetColThis.
   - Collision-safe: renames right-side key columns to avoid duplicate names.
   - Safe checks: verifies the right-side source column exists pre-join,
     then auto-detects what its name becomes after the join.
   - “Fill only when null/blank” or “overwrite all” toggle.

   HOW TO USE
   1) Edit the CONFIG block only (names are case-sensitive).
   2) If your keys are numbers on one side and text on the other, set KeyTypes*.
   3) If you still see unexpected nulls, check key values & types in both queries.

   COMMON GOTCHAS
   - Column names must match exactly (spaces, punctuation, hidden trailing spaces).
   - Data types on the join keys must be compatible (text ↔ text, number ↔ number).
   - If SourceColOther is itself a join key, it will land with the "__rK_" prefix.
   ============================================================== */

let
  // =========================
  // ========= CONFIG ========
  // =========================
  ThisTable         = #"Cpy Description -> Description",   // your current step/table
  OtherQuery        = #"AP_INVOICES_INTERFACE",                          // the other query (its NAME)
  KeysThis          = {"Index"},                           // key(s) in ThisTable (order matters)
  KeysOther         = {"Index"},                           // corresponding key(s) in OtherQuery (same order/length)
  TargetColThis     = "Item Description",                   // column to fill/overwrite in ThisTable
  SourceColOther    = "Description",                   // column to copy from in OtherQuery
  ReplaceNullsOnly  = true,                                // true = fill only blanks; false = overwrite all
  FromOtherNameBase = "__FromOther",                       // temp name for right-side source (if it isn't a key)

  // OPTIONAL: align key types *before* the join (uncomment & set if needed)
  // Example: if both sides use Int64 indices:
  // KeyTypesThis      = {Int64.Type},
  // KeyTypesOther     = {Int64.Type},

  // ===============================
  // ===== IMPLEMENTATION (no edits)
  // ===============================

  // 0) Left-side names and temp name that won’t collide
  LeftNames       = Table.ColumnNames(ThisTable),
  FromOtherName   = if List.Contains(LeftNames, FromOtherNameBase)
                    then FromOtherNameBase & "_r" else FromOtherNameBase,

  // 1) Right side: keep only keys + the source column we want
  //    MissingField.Ignore prevents hard errors if you typo a name—but we’ll validate next.
  OtherSlim0      = Table.SelectColumns(OtherQuery, List.Distinct(KeysOther & {SourceColOther}), MissingField.Ignore),

  // 1a) Guardrail: ensure the right-side *SourceColOther* actually exists pre-join.
  RightHasSource  = List.Contains(Table.ColumnNames(OtherSlim0), SourceColOther),
  _CheckSource    = if not RightHasSource then
                      error Error.Record(
                        "MissingSourceColumn",
                        "Right-side column '" & SourceColOther & "' was not found in the other query.",
                        [ RightColumns = Table.ColumnNames(OtherQuery) ]
                      )
                    else null,

  // 2) (Optional) align key types; uncomment CONFIG above if you need it.
  // ThisTableFixed  = if (try List.Count(KeyTypesThis) otherwise 0) = List.Count(KeysThis)
  //                   then Table.TransformColumnTypes(ThisTable, List.Zip({KeysThis, KeyTypesThis}))
  //                   else ThisTable,
  // OtherSlimFixed  = if (try List.Count(KeyTypesOther) otherwise 0) = List.Count(KeysOther)
  //                   then Table.TransformColumnTypes(OtherSlim0, List.Zip({KeysOther, KeyTypesOther}))
  //                   else OtherSlim0,

  // If you didn’t set KeyTypes*, we just pass through:
  ThisTableFixed  = ThisTable,
  OtherSlimFixed  = OtherSlim0,

  // 3) Collision-safe: rename right-side *key* columns so they won’t duplicate left names
  //    e.g., Index → __rK_Index (we’ll join using these renamed keys)
  KeyRenamePairs  = List.Transform(KeysOther, each {_, "__rK_" & _}),
  OtherKeysRenamed= Table.RenameColumns(OtherSlimFixed, KeyRenamePairs, MissingField.Ignore),
  KeysOtherRenamed= List.Transform(KeysOther, each "__rK_" & _),

  // 4) If the source column is NOT one of the keys, rename it to a known temp name
  OtherPrepared   = if List.Contains(KeysOther, SourceColOther)
                    then OtherKeysRenamed
                    else Table.RenameColumns(OtherKeysRenamed, {{SourceColOther, FromOtherName}}, MissingField.Ignore),

  // 5) Flat join (no nested tables) on left keys ↔ right renamed keys
  Joined0         = Table.Join(ThisTableFixed, KeysThis, OtherPrepared, KeysOtherRenamed, JoinKind.LeftOuter),

  // 6) Figure out what the source column is *called after the join*.
  //    It could be:
  //      - FromOtherName     (if we renamed a non-key source)
  //      - "__rK_" & SourceColOther (if the source is also a key)
  //      - SourceColOther    (if neither rename applied)
  RightNamesAfter = Table.ColumnNames(Joined0),
  Candidates      = { FromOtherName, "__rK_" & SourceColOther, SourceColOther },
  SourceAfterJoin =
      let hits = List.Select(Candidates, each List.Contains(RightNamesAfter, _))
      in  if List.Count(hits) > 0
          then hits{0}
          else error Error.Record(
                 "JoinedSourceMissing",
                 "After join, the source column was not found. Checked names: " & Text.Combine(Candidates, ", "),
                 [ JoinedColumns = RightNamesAfter,
                   RightColumnsPreJoin = Table.ColumnNames(OtherPrepared) ]
               ),

  // 7) Ensure the left target column exists (so ReplaceValue won’t fail)
  Joined          = if List.Contains(RightNamesAfter, TargetColThis)
                    then Joined0
                    else Table.AddColumn(Joined0, TargetColThis, each null),

  // 8) Fill/overwrite the target from the joined source
  Replaced        = if ReplaceNullsOnly
                    then Table.ReplaceValue(Joined, null, each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis})
                    else Table.ReplaceValue(Joined, each Record.Field(_, TargetColThis), each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis}),

  // 9) Clean up: drop the right-side renamed key columns and the temp source column
  DropCols        = List.Distinct(KeysOtherRenamed & {SourceAfterJoin}),
  Clean           = Table.RemoveColumns(Replaced, DropCols)
in
  Clean,
    #"Cpy Coding -> Distribution Combination" = /* ==============================================================
   ROBUST TEMPLATE: Fill/overwrite from ANOTHER query via flat join
   --------------------------------------------------------------
   WHAT THIS DOES
   - Left (ThisTable): your current query step.
   - Right (OtherQuery): some other query (its *name*; evaluates to its final step).
   - Joins on KeysThis ↔ KeysOther (1 or many columns).
   - Copies the right-side SourceColOther into the left-side TargetColThis.
   - Collision-safe: renames right-side key columns to avoid duplicate names.
   - Safe checks: verifies the right-side source column exists pre-join,
     then auto-detects what its name becomes after the join.
   - “Fill only when null/blank” or “overwrite all” toggle.

   HOW TO USE
   1) Edit the CONFIG block only (names are case-sensitive).
   2) If your keys are numbers on one side and text on the other, set KeyTypes*.
   3) If you still see unexpected nulls, check key values & types in both queries.

   COMMON GOTCHAS
   - Column names must match exactly (spaces, punctuation, hidden trailing spaces).
   - Data types on the join keys must be compatible (text ↔ text, number ↔ number).
   - If SourceColOther is itself a join key, it will land with the "__rK_" prefix.
   ============================================================== */

let
  // =========================
  // ========= CONFIG ========
  // =========================
  ThisTable         = #"Cpy Description -> Item Description",   // your current step/table
  OtherQuery        = #"Matched",                          // the other query (its NAME)
  KeysThis          = {"Index"},                           // key(s) in ThisTable (order matters)
  KeysOther         = {"Index"},                           // corresponding key(s) in OtherQuery (same order/length)
  TargetColThis     = "Distribution Combination",                   // column to fill/overwrite in ThisTable
  SourceColOther    = "Coding",                   // column to copy from in OtherQuery
  ReplaceNullsOnly  = true,                                // true = fill only blanks; false = overwrite all
  FromOtherNameBase = "__FromOther",                       // temp name for right-side source (if it isn't a key)

  // OPTIONAL: align key types *before* the join (uncomment & set if needed)
  // Example: if both sides use Int64 indices:
  // KeyTypesThis      = {Int64.Type},
  // KeyTypesOther     = {Int64.Type},

  // ===============================
  // ===== IMPLEMENTATION (no edits)
  // ===============================

  // 0) Left-side names and temp name that won’t collide
  LeftNames       = Table.ColumnNames(ThisTable),
  FromOtherName   = if List.Contains(LeftNames, FromOtherNameBase)
                    then FromOtherNameBase & "_r" else FromOtherNameBase,

  // 1) Right side: keep only keys + the source column we want
  //    MissingField.Ignore prevents hard errors if you typo a name—but we’ll validate next.
  OtherSlim0      = Table.SelectColumns(OtherQuery, List.Distinct(KeysOther & {SourceColOther}), MissingField.Ignore),

  // 1a) Guardrail: ensure the right-side *SourceColOther* actually exists pre-join.
  RightHasSource  = List.Contains(Table.ColumnNames(OtherSlim0), SourceColOther),
  _CheckSource    = if not RightHasSource then
                      error Error.Record(
                        "MissingSourceColumn",
                        "Right-side column '" & SourceColOther & "' was not found in the other query.",
                        [ RightColumns = Table.ColumnNames(OtherQuery) ]
                      )
                    else null,

  // 2) (Optional) align key types; uncomment CONFIG above if you need it.
  // ThisTableFixed  = if (try List.Count(KeyTypesThis) otherwise 0) = List.Count(KeysThis)
  //                   then Table.TransformColumnTypes(ThisTable, List.Zip({KeysThis, KeyTypesThis}))
  //                   else ThisTable,
  // OtherSlimFixed  = if (try List.Count(KeyTypesOther) otherwise 0) = List.Count(KeysOther)
  //                   then Table.TransformColumnTypes(OtherSlim0, List.Zip({KeysOther, KeyTypesOther}))
  //                   else OtherSlim0,

  // If you didn’t set KeyTypes*, we just pass through:
  ThisTableFixed  = ThisTable,
  OtherSlimFixed  = OtherSlim0,

  // 3) Collision-safe: rename right-side *key* columns so they won’t duplicate left names
  //    e.g., Index → __rK_Index (we’ll join using these renamed keys)
  KeyRenamePairs  = List.Transform(KeysOther, each {_, "__rK_" & _}),
  OtherKeysRenamed= Table.RenameColumns(OtherSlimFixed, KeyRenamePairs, MissingField.Ignore),
  KeysOtherRenamed= List.Transform(KeysOther, each "__rK_" & _),

  // 4) If the source column is NOT one of the keys, rename it to a known temp name
  OtherPrepared   = if List.Contains(KeysOther, SourceColOther)
                    then OtherKeysRenamed
                    else Table.RenameColumns(OtherKeysRenamed, {{SourceColOther, FromOtherName}}, MissingField.Ignore),

  // 5) Flat join (no nested tables) on left keys ↔ right renamed keys
  Joined0         = Table.Join(ThisTableFixed, KeysThis, OtherPrepared, KeysOtherRenamed, JoinKind.LeftOuter),

  // 6) Figure out what the source column is *called after the join*.
  //    It could be:
  //      - FromOtherName     (if we renamed a non-key source)
  //      - "__rK_" & SourceColOther (if the source is also a key)
  //      - SourceColOther    (if neither rename applied)
  RightNamesAfter = Table.ColumnNames(Joined0),
  Candidates      = { FromOtherName, "__rK_" & SourceColOther, SourceColOther },
  SourceAfterJoin =
      let hits = List.Select(Candidates, each List.Contains(RightNamesAfter, _))
      in  if List.Count(hits) > 0
          then hits{0}
          else error Error.Record(
                 "JoinedSourceMissing",
                 "After join, the source column was not found. Checked names: " & Text.Combine(Candidates, ", "),
                 [ JoinedColumns = RightNamesAfter,
                   RightColumnsPreJoin = Table.ColumnNames(OtherPrepared) ]
               ),

  // 7) Ensure the left target column exists (so ReplaceValue won’t fail)
  Joined          = if List.Contains(RightNamesAfter, TargetColThis)
                    then Joined0
                    else Table.AddColumn(Joined0, TargetColThis, each null),

  // 8) Fill/overwrite the target from the joined source
  Replaced        = if ReplaceNullsOnly
                    then Table.ReplaceValue(Joined, null, each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis})
                    else Table.ReplaceValue(Joined, each Record.Field(_, TargetColThis), each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis}),

  // 9) Clean up: drop the right-side renamed key columns and the temp source column
  DropCols        = List.Distinct(KeysOtherRenamed & {SourceAfterJoin}),
  Clean           = Table.RemoveColumns(Replaced, DropCols)
in
  Clean,
    #"Cpy Accounting Date -> Accounting Date" = /* ==============================================================
   ROBUST TEMPLATE: Fill/overwrite from ANOTHER query via flat join
   --------------------------------------------------------------
   WHAT THIS DOES
   - Left (ThisTable): your current query step.
   - Right (OtherQuery): some other query (its *name*; evaluates to its final step).
   - Joins on KeysThis ↔ KeysOther (1 or many columns).
   - Copies the right-side SourceColOther into the left-side TargetColThis.
   - Collision-safe: renames right-side key columns to avoid duplicate names.
   - Safe checks: verifies the right-side source column exists pre-join,
     then auto-detects what its name becomes after the join.
   - “Fill only when null/blank” or “overwrite all” toggle.

   HOW TO USE
   1) Edit the CONFIG block only (names are case-sensitive).
   2) If your keys are numbers on one side and text on the other, set KeyTypes*.
   3) If you still see unexpected nulls, check key values & types in both queries.

   COMMON GOTCHAS
   - Column names must match exactly (spaces, punctuation, hidden trailing spaces).
   - Data types on the join keys must be compatible (text ↔ text, number ↔ number).
   - If SourceColOther is itself a join key, it will land with the "__rK_" prefix.
   ============================================================== */

let
  // =========================
  // ========= CONFIG ========
  // =========================
  ThisTable         = #"Cpy Coding -> Distribution Combination",   // your current step/table
  OtherQuery        = #"AP_INVOICES_INTERFACE",                          // the other query (its NAME)
  KeysThis          = {"Index"},                           // key(s) in ThisTable (order matters)
  KeysOther         = {"Index"},                           // corresponding key(s) in OtherQuery (same order/length)
  TargetColThis     = "Accounting Date",                   // column to fill/overwrite in ThisTable
  SourceColOther    = "Accounting Date",                   // column to copy from in OtherQuery
  ReplaceNullsOnly  = true,                                // true = fill only blanks; false = overwrite all
  FromOtherNameBase = "__FromOther",                       // temp name for right-side source (if it isn't a key)

  // OPTIONAL: align key types *before* the join (uncomment & set if needed)
  // Example: if both sides use Int64 indices:
  // KeyTypesThis      = {Int64.Type},
  // KeyTypesOther     = {Int64.Type},

  // ===============================
  // ===== IMPLEMENTATION (no edits)
  // ===============================

  // 0) Left-side names and temp name that won’t collide
  LeftNames       = Table.ColumnNames(ThisTable),
  FromOtherName   = if List.Contains(LeftNames, FromOtherNameBase)
                    then FromOtherNameBase & "_r" else FromOtherNameBase,

  // 1) Right side: keep only keys + the source column we want
  //    MissingField.Ignore prevents hard errors if you typo a name—but we’ll validate next.
  OtherSlim0      = Table.SelectColumns(OtherQuery, List.Distinct(KeysOther & {SourceColOther}), MissingField.Ignore),

  // 1a) Guardrail: ensure the right-side *SourceColOther* actually exists pre-join.
  RightHasSource  = List.Contains(Table.ColumnNames(OtherSlim0), SourceColOther),
  _CheckSource    = if not RightHasSource then
                      error Error.Record(
                        "MissingSourceColumn",
                        "Right-side column '" & SourceColOther & "' was not found in the other query.",
                        [ RightColumns = Table.ColumnNames(OtherQuery) ]
                      )
                    else null,

  // 2) (Optional) align key types; uncomment CONFIG above if you need it.
  // ThisTableFixed  = if (try List.Count(KeyTypesThis) otherwise 0) = List.Count(KeysThis)
  //                   then Table.TransformColumnTypes(ThisTable, List.Zip({KeysThis, KeyTypesThis}))
  //                   else ThisTable,
  // OtherSlimFixed  = if (try List.Count(KeyTypesOther) otherwise 0) = List.Count(KeysOther)
  //                   then Table.TransformColumnTypes(OtherSlim0, List.Zip({KeysOther, KeyTypesOther}))
  //                   else OtherSlim0,

  // If you didn’t set KeyTypes*, we just pass through:
  ThisTableFixed  = ThisTable,
  OtherSlimFixed  = OtherSlim0,

  // 3) Collision-safe: rename right-side *key* columns so they won’t duplicate left names
  //    e.g., Index → __rK_Index (we’ll join using these renamed keys)
  KeyRenamePairs  = List.Transform(KeysOther, each {_, "__rK_" & _}),
  OtherKeysRenamed= Table.RenameColumns(OtherSlimFixed, KeyRenamePairs, MissingField.Ignore),
  KeysOtherRenamed= List.Transform(KeysOther, each "__rK_" & _),

  // 4) If the source column is NOT one of the keys, rename it to a known temp name
  OtherPrepared   = if List.Contains(KeysOther, SourceColOther)
                    then OtherKeysRenamed
                    else Table.RenameColumns(OtherKeysRenamed, {{SourceColOther, FromOtherName}}, MissingField.Ignore),

  // 5) Flat join (no nested tables) on left keys ↔ right renamed keys
  Joined0         = Table.Join(ThisTableFixed, KeysThis, OtherPrepared, KeysOtherRenamed, JoinKind.LeftOuter),

  // 6) Figure out what the source column is *called after the join*.
  //    It could be:
  //      - FromOtherName     (if we renamed a non-key source)
  //      - "__rK_" & SourceColOther (if the source is also a key)
  //      - SourceColOther    (if neither rename applied)
  RightNamesAfter = Table.ColumnNames(Joined0),
  Candidates      = { FromOtherName, "__rK_" & SourceColOther, SourceColOther },
  SourceAfterJoin =
      let hits = List.Select(Candidates, each List.Contains(RightNamesAfter, _))
      in  if List.Count(hits) > 0
          then hits{0}
          else error Error.Record(
                 "JoinedSourceMissing",
                 "After join, the source column was not found. Checked names: " & Text.Combine(Candidates, ", "),
                 [ JoinedColumns = RightNamesAfter,
                   RightColumnsPreJoin = Table.ColumnNames(OtherPrepared) ]
               ),

  // 7) Ensure the left target column exists (so ReplaceValue won’t fail)
  Joined          = if List.Contains(RightNamesAfter, TargetColThis)
                    then Joined0
                    else Table.AddColumn(Joined0, TargetColThis, each null),

  // 8) Fill/overwrite the target from the joined source
  Replaced        = if ReplaceNullsOnly
                    then Table.ReplaceValue(Joined, null, each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis})
                    else Table.ReplaceValue(Joined, each Record.Field(_, TargetColThis), each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis}),

  // 9) Clean up: drop the right-side renamed key columns and the temp source column
  DropCols        = List.Distinct(KeysOtherRenamed & {SourceAfterJoin}),
  Clean           = Table.RemoveColumns(Replaced, DropCols)
in
  Clean,
    #"Fill Expenditure Organization -> """"" = /* TEMPLATE: Fill/overwrite a column with a single scalar value
   HOW TO USE
   - Edit the CONFIG block only.
   - Works for text/number/date/etc. (set ValueToUse accordingly).
*/
/* TEMPLATE: Fill/overwrite a column with a single scalar value
   HOW TO USE
   - Edit the CONFIG block only.
   - Works for text/number/date/etc. (set ValueToUse accordingly).
*/
let
    // =========================
    // ========= CONFIG ========
    // =========================
    TableIn          = #"Cpy Accounting Date -> Accounting Date",        // prior step/table in THIS query
    TargetCol        = "Expenditure Organization",               // column to fill/overwrite
    ReplaceNullsOnly = false,                   // true = only fill nulls; false = overwrite all rows
// The value to write (examples):
    //   "Approved"        // text
    //   0                 // number
    //   #date(2025,10,7)  // date
    //   #datetime(2025,10,7,0,0,0)
    ValueToUse       = "",
// Optional: declare the column type you want (set to null to skip)
    TargetType       = type text,
// ===============================
    // ===== IMPLEMENTATION (no edits)
    // ===============================
    // Ensure target column exists (so ReplaceValue won't error)
    WithTarget =
        if List.Contains(Table.ColumnNames(TableIn), TargetCol)
        then TableIn
        else Table.AddColumn(TableIn, TargetCol, each null),
// Optionally coerce the target column's type
    Typed =
        if TargetType <> null
        then Table.TransformColumnTypes(WithTarget, {{TargetCol, TargetType}})
        else WithTarget,
Result =
        if ReplaceNullsOnly then
            Table.ReplaceValue(
                Typed,
                null,
                each ValueToUse,
                Replacer.ReplaceValue,
                {TargetCol}
            )
        else
            Table.ReplaceValue(
                Typed,
                each Record.Field(_, TargetCol),
                each ValueToUse,
                Replacer.ReplaceValue,
                {TargetCol}
            )
in
    Result,
    #"Delete extra rows" = /* TEMPLATE: Delete rows when ANY/ALL of selected columns are empty
   HOW TO USE:
   1) Edit the CONFIG block only.
   2) Set DeleteMode to "Any" or "All".
   3) Choose what counts as "empty" (nulls, blank text, zero numbers).
*/
/* TEMPLATE: Delete rows when ANY/ALL of selected columns are empty
   HOW TO USE:
   1) Edit the CONFIG block only.
   2) Set DeleteMode to "Any" or "All".
   3) Choose what counts as "empty" (nulls, blank text, zero numbers).
*/
let
  // =========================
  // ========= CONFIG ========
  // =========================
  TableIn                   = #"Fill Expenditure Organization -> """"",   // prior step in THIS query
  ColumnsToCheck            = {"Item Description", "Description"},  // columns to test for emptiness
  DeleteMode                = "All",             // "Any" -> delete if any checked column is empty
                                                  // "All" -> delete if all checked columns are empty
  TreatNullAsEmpty          = true,              // nulls count as empty
  TreatBlankTextAsEmpty     = true,              // "" or whitespace-only text counts as empty
  TreatZeroNumberAsEmpty    = false,             // 0 counts as empty (numbers only)

  // ===============================
  // ===== IMPLEMENTATION (no edits)
  // ===============================
  // Only keep columns that actually exist (avoid errors if a name is wrong/missing)
  ExistingCols              = List.Intersect({ColumnsToCheck, Table.ColumnNames(TableIn)}),
  MissingCols               = List.Difference(ColumnsToCheck, ExistingCols),

  // Row-level emptiness test for a single value, honoring the config above
  IsEmptyValue = (v as any) as logical =>
    let
      isNull      = TreatNullAsEmpty and (v = null),
      isBlankText = TreatBlankTextAsEmpty and Value.Is(v, type text) and (Text.Trim(v) = ""),
      isZeroNum   = TreatZeroNumberAsEmpty and Value.Is(v, type number) and (v = 0)
    in
      isNull or isBlankText or isZeroNum,

  // Keep row if NOT slated for deletion
  KeepRow = (r as record) as logical =>
    let
      // Safely read each column (missing columns yield null here)
      vals        = List.Transform(ColumnsToCheck, each Record.FieldOrDefault(r, _, null)),
      empties     = List.Transform(vals, each IsEmptyValue(_)),
      deleteThis  = if DeleteMode = "Any" then List.AnyTrue(empties) else List.AllTrue(empties)
    in
      not deleteThis,

  Result =
    if List.Count(ExistingCols) = 0
    then TableIn                 // nothing to check -> return as-is
    else Table.SelectRows(TableIn, each KeepRow(_))
in
  Result
in
    #"Delete extra rows"