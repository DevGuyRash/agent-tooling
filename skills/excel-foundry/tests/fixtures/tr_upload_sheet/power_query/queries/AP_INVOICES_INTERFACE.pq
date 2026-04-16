let
    Source = Excel.Workbook(File.Contents("C:\Users\E135328\Documents\Templates\Base\T&R UPLOAD TEMPLATE.xlsm"), null, true),
    AP_INVOICES_INTERFACE_Sheet = Source{[Item="AP_INVOICES_INTERFACE",Kind="Sheet"]}[Data],
    #"Removed Top Rows" = Table.Skip(AP_INVOICES_INTERFACE_Sheet,3),
    #"Promoted Headers" = Table.PromoteHeaders(#"Removed Top Rows", [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{{"*Invoice ID", Int64.Type}, {"*Business Unit", type text}, {"*Source", type text}, {"*Invoice Number", type any}, {"*Invoice Amount", type any}, {"*Invoice Date", type any}, {"**Supplier Name", type any}, {"**Supplier Number", type any}, {"*Supplier Site", type text}, {"Invoice Currency ", type text}, {"Payment Currency", type text}, {"Description", type any}, {"Import Set", type any}, {"*Invoice Type", type text}, {"Legal Entity", type text}, {"Customer Tax Registration Number", type any}, {"Customer Registration Code", type any}, {"First-Party Tax Registration Number", type any}, {"Supplier Tax Registration Number", type any}, {"*Payment Terms", type any}, {"Terms Date", type any}, {"Goods Received Date", type any}, {"Invoice Received Date", type any}, {"Accounting Date", type any}, {"Payment Method", type any}, {"Pay Group", type any}, {"Pay Alone", type any}, {"Discountable Amount", type any}, {"Prepayment Number", type any}, {"Prepayment Line Number", type any}, {"Prepayment Application Amount", type any}, {"Prepayment Accounting Date", type any}, {"Invoice Includes Prepayment", type any}, {"Conversion Rate Type", type any}, {"Conversion Date", type any}, {"Conversion Rate", type any}, {"Liability Combination", type any}, {"Document Category Code", type any}, {"Voucher Number", type any}, {"Requester First Name", type any}, {"Requester Last Name", type any}, {"Requester Employee Number", type any}, {"Delivery Channel Code", type any}, {"Bank Charge Bearer", type any}, {"Remit-to Supplier", type any}, {"Remit-to Supplier Number", type any}, {"Remit-to Address Name", type any}, {"Payment Priority", type any}, {"Settlement Priority", type any}, {"Unique Remittance Identifier", type any}, {"Unique Remittance Identifier Check Digit", type any}, {"Payment Reason Code", type any}, {"Payment Reason Comments", type any}, {"Remittance Message 1", type any}, {"Remittance Message 2", type any}, {"Remittance Message 3", type any}, {"Withholding Tax Group", type any}, {"Ship-to Location", type any}, {"Taxation Country", type any}, {"Document Sub Type", type any}, {"Tax Invoice Internal Sequence Number", type any}, {"Supplier Tax Invoice Number", type any}, {"Tax Invoice Recording Date", type any}, {"Supplier Tax Invoice Date", type any}, {"Supplier Tax Invoice Conversion Rate", type any}, {"Port Of Entry Code", type any}, {"Correction Year", type any}, {"Correction Period", type any}, {"Import Document Number", type any}, {"Import Document Date", type any}, {"Tax Control Amount", type any}, {"Calculate Tax During Import", type any}, {"Add Tax To Invoice Amount", type any}, {"Attribute Category", type any}, {"Attribute 1", type any}, {"Attribute 2", type any}, {"Attribute 3", type any}, {"Attribute 4", type any}, {"Attribute 5", type any}, {"Attribute 6", type any}, {"Attribute 7", type any}, {"Attribute 8", type any}, {"Attribute 9", type any}, {"Attribute 10", type any}, {"Attribute 11", type any}, {"Attribute 12", type any}, {"Attribute 13", type any}, {"Attribute 14", type any}, {"Attribute 15", type any}, {"Attribute Number 1", type any}, {"Attribute Number 2", type any}, {"Attribute Number 3", type any}, {"Attribute Number 4", type any}, {"Attribute Number 5", type any}, {"Attribute Date 1", type any}, {"Attribute Date 2", type any}, {"Attribute Date 3", type any}, {"Attribute Date 4", type any}, {"Attribute Date 5", type any}, {"Global Attribute Category", type any}, {"Global Attribute 1", type any}, {"Global Attribute 2", type any}, {"Global Attribute 3", type any}, {"Global Attribute 4", type any}, {"Global Attribute 5", type any}, {"Global Attribute 6", type any}, {"Global Attribute 7", type any}, {"Global Attribute 8", type any}, {"Global Attribute 9", type any}, {"Global Attribute 10", type any}, {"Global Attribute 11", type any}, {"Global Attribute 12", type any}, {"Global Attribute 13", type any}, {"Global Attribute 14", type any}, {"Global Attribute 15", type any}, {"Global Attribute 16", type any}, {"Global Attribute 17", type any}, {"Global Attribute 18", type any}, {"Global Attribute 19", type any}, {"Global Attribute 20", type any}, {"Global Attribute Number 1", type any}, {"Global Attribute Number 2", type any}, {"Global Attribute Number 3", type any}, {"Global Attribute Number 4", type any}, {"Global Attribute Number 5", type any}, {"Global Attribute Date 1", type any}, {"Global Attribute Date 2", type any}, {"Global Attribute Date 3", type any}, {"Global Attribute Date 4", type any}, {"Global Attribute Date 5", type any}}),
    #"Added Index" = Table.AddIndexColumn(#"Changed Type", "Index", 0, 1, Int64.Type),
    #"Cpy VendorID -> Supplier Number" = /* TEMPLATE: overwrite/fill a column from another column in the SAME query */
/* TEMPLATE: fill/overwrite from ANOTHER query’s column via keys */
/* Robust join + fill template */
/* TEMPLATE: Fill/overwrite a column from ANOTHER query using a flat join (Table.Join)
   HOW TO USE:
   1) Edit the CONFIG block only.
   2) Works with single or multi-column keys.
   3) Set ReplaceNullsOnly = true to only fill blanks; false to overwrite all rows.
*/
/* TEMPLATE: Fill/overwrite a column from ANOTHER query using a flat join (collision-safe)

   WHAT IT DOES
   - Renames right-side (OtherQuery) key columns so they don't collide with left-side names.
   - Optionally renames the right-side source column to a temp name.
   - Joins, fills/overwrites the target, then removes the temp columns.

   HOW TO USE
   - Edit only the CONFIG block.
   - KeysThis/KeysOther can be single or multiple keys (orders must match).
   - Set ReplaceNullsOnly = true to only fill blanks; false to overwrite all.
*/
let
    // ========= CONFIG =========
    ThisTable         = #"Added Index",          // your current step/table
    OtherQuery        = #"Matched",              // the other query (its name; resolves to final step)
    KeysThis          = {"Index"},               // key(s) in ThisTable
    KeysOther         = {"Index"},               // corresponding key(s) in OtherQuery
    TargetColThis     = "**Supplier Number",     // column to fill/overwrite in ThisTable
    SourceColOther    = "VendorId",              // column to copy from in OtherQuery
    ReplaceNullsOnly  = true,                    // true=fill only nulls; false=overwrite all
    FromOtherNameBase = "__FromOther",           // preferred temp name; will auto-unique if needed

    // Optional: align key types (uncomment & set as needed)
    // KeyTypesThis      = {Int64.Type},
    // KeyTypesOther     = {Int64.Type},

    // ===== Implementation (no edits) =====
    LeftNames         = Table.ColumnNames(ThisTable),

    // If temp name collides with left, tweak it
    FromOtherName     = if List.Contains(LeftNames, FromOtherNameBase) then FromOtherNameBase & "_r" else FromOtherNameBase,

    // Keep only keys + source from the right side
    OtherSlim         = Table.SelectColumns(OtherQuery, List.Distinct(KeysOther & {SourceColOther}), MissingField.Ignore),

    // (Optional) Align key types — uncomment if you set KeyTypes* above
    // ThisTableFixed     = if (try List.Count(KeyTypesThis) otherwise 0) = List.Count(KeysThis)
    //                     then Table.TransformColumnTypes(ThisTable, List.Zip({KeysThis, KeyTypesThis}))
    //                     else ThisTable,
    // OtherSlimFixed     = if (try List.Count(KeyTypesOther) otherwise 0) = List.Count(KeysOther)
    //                     then Table.TransformColumnTypes(OtherSlim, List.Zip({KeysOther, KeyTypesOther}))
    //                     else OtherSlim,

    ThisTableFixed    = ThisTable,
    OtherSlimFixed    = OtherSlim,

    // Rename right-side keys to avoid duplicates (e.g., Index -> __rK_Index)
    KeyRenamePairs    = List.Transform(KeysOther, each {_, "__rK_" & _}),
    OtherKeysRenamed  = Table.RenameColumns(OtherSlimFixed, KeyRenamePairs, MissingField.Ignore),
    KeysOtherRenamed  = List.Transform(KeysOther, each "__rK_" & _),

    // If SourceColOther is NOT a key, rename it to a safe temp name to avoid collisions
    OtherPrepared     = if List.Contains(KeysOther, SourceColOther)
                        then OtherKeysRenamed
                        else Table.RenameColumns(OtherKeysRenamed, {{SourceColOther, FromOtherName}}, MissingField.Ignore),

    // Determine the source column name AFTER the rename logic
    SourceAfterJoin   = if List.Contains(KeysOther, SourceColOther)
                        then "__rK_" & SourceColOther
                        else FromOtherName,

    // Flat join with collision-safe right-side column names
    Joined0           = Table.Join(ThisTableFixed, KeysThis, OtherPrepared, KeysOtherRenamed, JoinKind.LeftOuter),

    // Ensure the target column exists
    Joined            = if List.Contains(Table.ColumnNames(Joined0), TargetColThis)
                        then Joined0
                        else Table.AddColumn(Joined0, TargetColThis, each null),

    // Fill/overwrite target from the joined source column
    Replaced          = if ReplaceNullsOnly
                        then Table.ReplaceValue(Joined, null, each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis})
                        else Table.ReplaceValue(Joined, each Record.Field(_, TargetColThis), each Record.Field(_, SourceAfterJoin), Replacer.ReplaceValue, {TargetColThis}),

    // Drop the right-side key duplicates and the temp source column
    DropCols          = List.Distinct(KeysOtherRenamed & {SourceAfterJoin}),
    Clean             = Table.RemoveColumns(Replaced, DropCols)
in
    Clean,
    #"Cpy As-Of Date -> *Invoice Date" = /* TEMPLATE: Fill/overwrite a DATE column using a base date + offsets
   HOW TO USE
   - Edit the CONFIG block only.
   - Choose where the base date comes from (Column / Today / Fixed).
   - Offsets can be negative or positive; defaults are 0.
*/
/* TEMPLATE: Fill/overwrite a DATE column using base date + offsets + optional formatting
   HOW TO USE:
   - If DateFormat = null → writes a true date type.
   - If DateFormat is a string (e.g., "yyyy-MM-dd") → writes formatted TEXT.
*/
/* TEMPLATE: Fill/overwrite a DATE column using base date + offsets + optional formatting
   HOW TO USE:
   - If DateFormat = null → writes a true date type.
   - If DateFormat is a string (e.g., "yyyy-MM-dd") → writes formatted TEXT.
*/
/* ==============================================================
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
  ThisTable         = #"Cpy VendorID -> Supplier Number",   // your current step/table
  OtherQuery        = #"Matched",                          // the other query (its NAME)
  KeysThis          = {"Index"},                           // key(s) in ThisTable (order matters)
  KeysOther         = {"Index"},                           // corresponding key(s) in OtherQuery (same order/length)
  TargetColThis     = "*Invoice Date",                   // column to fill/overwrite in ThisTable
  SourceColOther    = "As-Of Date",                   // column to copy from in OtherQuery
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
    #"Set Invoice Received Date -> Today" = let
  // =========================
  // ========= CONFIG ========
  // =========================
  TableIn            = #"Cpy As-Of Date -> *Invoice Date",   // prior step/table in THIS query
  TargetCol          = "Invoice Received Date",               // date/text column to fill/overwrite
  ReplaceNullsOnly   = true,                                  // true = only fill nulls; false = overwrite all

  // Base-date source: "Column" | "Today" | "Fixed"
  BaseDateMode       = "Today",
  BaseDateCol        = "OrderDate",                           // used when BaseDateMode = "Column"
  BaseDateFixed      = #date(2025, 1, 1),                     // used when BaseDateMode = "Fixed"

  // Offsets
  YearsOffset        = 0,
  MonthsOffset       = 0,
  DaysOffset         = 0,

  // Formatting (null = keep as date type; otherwise outputs text with this format)
  DateFormat         = "yyyy/MM/dd",                          // set to null to keep as date type
  DateCulture        = null,                                  // e.g., "en-US"; null = current locale

  // --- Invoice-date override (minimal add) ---
  // If the invoice date's month is earlier than the current month, force base to that invoice date.
  InvoiceDateCol               = "*Invoice Date",
  BypassInvoiceMonthOverride   = false,

  // ===============================
  // ===== IMPLEMENTATION (with invoice-month hook)
  // ===============================
  // Decide final type from DateFormat
  TargetTypeActual   = if DateFormat = null then type date else type text,

  EnsureTarget =
    if List.Contains(Table.ColumnNames(TableIn), TargetCol)
    then TableIn
    else Table.AddColumn(TableIn, TargetCol, each null, TargetTypeActual),

  WithType =
    Table.TransformColumnTypes(EnsureTarget, {{TargetCol, TargetTypeActual}}),

  // Precompute current month start once
  TodayLocalDate       = Date.From(DateTime.LocalNow()),
  StartOfThisMonth     = Date.StartOfMonth(TodayLocalDate),

  // Compute the (possibly formatted) date per row
  ComputeOut = (r as record) as any =>
    let
      invRaw   = try Record.Field(r, InvoiceDateCol) otherwise null,
      invDate  = try Date.From(invRaw) otherwise null,
      invPast  = if invDate <> null then Date.StartOfMonth(invDate) < StartOfThisMonth else false,
      useInv   = (not BypassInvoiceMonthOverride) and invPast,

      baseRaw  =
        if useInv then invDate
        else if BaseDateMode = "Column" then try Record.Field(r, BaseDateCol) otherwise null
        else if BaseDateMode = "Today"  then TodayLocalDate
        else if BaseDateMode = "Fixed"  then BaseDateFixed
        else null,

      baseDate = try Date.From(baseRaw) otherwise null,
      afterY   = if baseDate <> null then Date.AddYears(baseDate,  YearsOffset) else null,
      afterM   = if afterY   <> null then Date.AddMonths(afterY,   MonthsOffset) else null,
      afterD   = if afterM   <> null then Date.AddDays(afterM,     DaysOffset) else null,

      output   =
        if afterD = null then null
        else if DateFormat = null then afterD
        else if DateCulture = null then Date.ToText(afterD, DateFormat)
        else Date.ToText(afterD, DateFormat, DateCulture)
    in
      output,

  Result =
    if ReplaceNullsOnly then
      Table.ReplaceValue(WithType, null, each ComputeOut(_), Replacer.ReplaceValue, {TargetCol})
    else
      Table.ReplaceValue(WithType, each Record.Field(_, TargetCol), each ComputeOut(_), Replacer.ReplaceValue, {TargetCol})
in
  Result,
    #"Set Accounting Date -> Today" = let
  // =========================
  // ========= CONFIG ========
  // =========================
  TableIn            = #"Set Invoice Received Date -> Today", // prior step/table in THIS query
  TargetCol          = "Accounting Date",                     // date/text column to fill/overwrite
  ReplaceNullsOnly   = true,                                  // true = only fill nulls; false = overwrite all

  // Base-date source: "Column" | "Today" | "Fixed"
  BaseDateMode       = "Today",
  BaseDateCol        = "OrderDate",                           // used when BaseDateMode = "Column"
  BaseDateFixed      = #date(2025, 1, 1),                     // used when BaseDateMode = "Fixed"

  // Offsets
  YearsOffset        = 0,
  MonthsOffset       = 0,
  DaysOffset         = 0,

  // Formatting (null = keep as date type; otherwise outputs text with this format)
  DateFormat         = "yyyy/MM/dd",                          // set to null to keep as date type
  DateCulture        = null,                                  // e.g., "en-US"; null = current locale

  // --- Invoice-date override (minimal add) ---
  InvoiceDateCol               = "*Invoice Date",
  BypassInvoiceMonthOverride   = false,

  // ===============================
  // ===== IMPLEMENTATION (with invoice-month hook)
  // ===============================
  TargetTypeActual   = if DateFormat = null then type date else type text,

  EnsureTarget =
    if List.Contains(Table.ColumnNames(TableIn), TargetCol)
    then TableIn
    else Table.AddColumn(TableIn, TargetCol, each null, TargetTypeActual),

  WithType =
    Table.TransformColumnTypes(EnsureTarget, {{TargetCol, TargetTypeActual}}),

  TodayLocalDate       = Date.From(DateTime.LocalNow()),
  StartOfThisMonth     = Date.StartOfMonth(TodayLocalDate),

  ComputeOut = (r as record) as any =>
    let
      invRaw   = try Record.Field(r, InvoiceDateCol) otherwise null,
      invDate  = try Date.From(invRaw) otherwise null,
      invPast  = if invDate <> null then Date.StartOfMonth(invDate) < StartOfThisMonth else false,
      useInv   = (not BypassInvoiceMonthOverride) and invPast,

      baseRaw  =
        if useInv then invDate
        else if BaseDateMode = "Column" then try Record.Field(r, BaseDateCol) otherwise null
        else if BaseDateMode = "Today"  then TodayLocalDate
        else if BaseDateMode = "Fixed"  then BaseDateFixed
        else null,

      baseDate = try Date.From(baseRaw) otherwise null,
      afterY   = if baseDate <> null then Date.AddYears(baseDate,  YearsOffset) else null,
      afterM   = if afterY   <> null then Date.AddMonths(afterY,   MonthsOffset) else null,
      afterD   = if afterM   <> null then Date.AddDays(afterM,     DaysOffset) else null,

      output   =
        if afterD = null then null
        else if DateFormat = null then afterD
        else if DateCulture = null then Date.ToText(afterD, DateFormat)
        else Date.ToText(afterD, DateFormat, DateCulture)
    in
      output,

  Result =
    if ReplaceNullsOnly then
      Table.ReplaceValue(WithType, null, each ComputeOut(_), Replacer.ReplaceValue, {TargetCol})
    else
      Table.ReplaceValue(WithType, each Record.Field(_, TargetCol), each ComputeOut(_), Replacer.ReplaceValue, {TargetCol})
in
  Result,
    #"Set Pay Alone -> Y" = /* TEMPLATE: Fill/overwrite a column with a single scalar value
   HOW TO USE
   - Edit the CONFIG block only.
   - Works for text/number/date/etc. (set ValueToUse accordingly).
*/
let
    // =========================
    // ========= CONFIG ========
    // =========================
    TableIn          = #"Set Accounting Date -> Today",        // prior step/table in THIS query
    TargetCol        = "Pay Alone",               // column to fill/overwrite
    ReplaceNullsOnly = true,                   // true = only fill nulls; false = overwrite all rows
// The value to write (examples):
    //   "Approved"        // text
    //   0                 // number
    //   #date(2025,10,7)  // date
    //   #datetime(2025,10,7,0,0,0)
    ValueToUse       = "Y",
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
    #"Set *Payment Terms -> Immediate" = /* TEMPLATE: Fill/overwrite a column with a single scalar value
   HOW TO USE
   - Edit the CONFIG block only.
   - Works for text/number/date/etc. (set ValueToUse accordingly).
*/
let
    // =========================
    // ========= CONFIG ========
    // =========================
    TableIn          = #"Set Pay Alone -> Y",        // prior step/table in THIS query
    TargetCol        = "*Payment Terms",               // column to fill/overwrite
    ReplaceNullsOnly = true,                   // true = only fill nulls; false = overwrite all rows
// The value to write (examples):
    //   "Approved"        // text
    //   0                 // number
    //   #date(2025,10,7)  // date
    //   #datetime(2025,10,7,0,0,0)
    ValueToUse       = "Immediate",
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
    #"Set Import Set -> Fixed + Date" = /* TEMPLATE: Fill a column with <Value> + <Separator> + <Date>, with order swap
   HOW TO USE: edit the CONFIG block only.
*/
/* TEMPLATE: Fill a column with <Value> + <Separator> + <Date>, with order swap
   HOW TO USE: edit the CONFIG block only.
*/
/* ROBUST TEMPLATE: Fill/overwrite from ANOTHER query via flat join (with column checks) */
/* TEMPLATE: Replace a token in Target with the LAST whitespace-token from Source (local, in-place)
   Use-case example (edit in CONFIG):
     - SearchText    = "VIN-STOCK"
     - TargetCol     = "Description"
     - SourceCol     = "Clearing"
*/
/* TEMPLATE: Fill a column with <Value> + <Separator> + <Date>, with order swap
   HOW TO USE: edit the CONFIG block only.
*/
let
  // =========================
  // ========= CONFIG ========
  // =========================
  TableIn            = #"Set *Payment Terms -> Immediate",       // previous step in THIS query
  TargetCol          = "Import Set",           // column to fill/overwrite (created if missing)
  ReplaceNullsOnly   = true,                   // true = only fill nulls; false = overwrite all

  // ----- VALUE source -----
  // Choose: "Fixed" | "Column"
  ValueMode          = "Fixed",
  ValueFixed         = "PREAUTHAK",            // used when ValueMode = "Fixed"
  ValueCol           = "StatusBase",           // used when ValueMode = "Column"

  // ----- DATE source -----
  // Choose: "Column" | "Today" | "Fixed" | "None"
  BaseDateMode       = "Today",
  BaseDateCol        = "OrderDate",            // used when BaseDateMode = "Column"
  BaseDateFixed      = #date(2025, 1, 1),      // used when BaseDateMode = "Fixed"

  // Date Offsets (can be negative)
  YearsOffset        = 0,
  MonthsOffset       = 0,
  DaysOffset         = 0,

  // Date formatting (see Date.ToText). If you want locale-aware month names, set DateCulture (e.g., "en-US").
  DateFormat         = "MM.dd.yyyy",
  DateCulture        = null,

  // Separator between value and date (used only when BOTH parts exist)
  Separator          = " ",

  // Output order: "ValueDate" or "DateValue"
  OrderMode          = "ValueDate",

  // Final column type (we're concatenating → text is typical)
  TargetType         = type text,

  // --- Invoice-date override (minimal add) ---
  InvoiceDateCol               = "*Invoice Date",
  BypassInvoiceMonthOverride   = false,

  // ===============================
  // ===== IMPLEMENTATION (with invoice-month hook)
  // ===============================
  EnsureTarget =
    if List.Contains(Table.ColumnNames(TableIn), TargetCol)
    then TableIn
    else Table.AddColumn(TableIn, TargetCol, each null),

  WithType =
    if TargetType <> null
    then Table.TransformColumnTypes(EnsureTarget, {{TargetCol, TargetType}})
    else EnsureTarget,

  // Precompute current month start once
  TodayLocalDate       = Date.From(DateTime.LocalNow()),
  StartOfThisMonth     = Date.StartOfMonth(TodayLocalDate),

  // Value → text
  GetValueText = (r as record) as nullable text =>
    let
      raw  = if ValueMode = "Column"
             then try Record.Field(r, ValueCol) otherwise null
             else ValueFixed,
      text = if raw = null then null else Text.From(raw)
    in
      text,

  // Date → offsets → formatted text
  // NOTE: override uses invoice date even if BaseDateMode = "None"
  GetDateText = (r as record) as nullable text =>
    let
      invRaw   = try Record.Field(r, InvoiceDateCol) otherwise null,
      invDate  = try Date.From(invRaw) otherwise null,
      invPast  = if invDate <> null then Date.StartOfMonth(invDate) < StartOfThisMonth else false,
      useInv   = (not BypassInvoiceMonthOverride) and invPast,

      baseRaw  =
        if useInv then invDate
        else if BaseDateMode = "Column" then try Record.Field(r, BaseDateCol) otherwise null
        else if BaseDateMode = "Today"  then TodayLocalDate
        else if BaseDateMode = "Fixed"  then BaseDateFixed
        else null, // "None"

      baseDate = try Date.From(baseRaw) otherwise null,
      afterY   = if baseDate <> null then Date.AddYears(baseDate,  YearsOffset) else null,
      afterM   = if afterY   <> null then Date.AddMonths(afterY,   MonthsOffset) else null,
      afterD   = if afterM   <> null then Date.AddDays(afterM,     DaysOffset) else null,

      dText    =
        if afterD = null then null
        else if DateCulture = null then Date.ToText(afterD, DateFormat)
        else Date.ToText(afterD, DateFormat, DateCulture)
    in
      dText,

  // Compose in requested order; use Separator only when both parts exist
  ComposeText = (r as record) as nullable text =>
    let
      v = GetValueText(r),
      d = GetDateText(r),
      partsVD = List.RemoveNulls({v, d}),
      partsDV = List.RemoveNulls({d, v}),
      parts   = if OrderMode = "DateValue" then partsDV else partsVD,
      result  = if List.Count(parts) = 0 then null
                else if List.Count(parts) = 1 then parts{0}
                else Text.Combine(parts, Separator)
    in
      result,

  Result =
    if ReplaceNullsOnly then
      Table.ReplaceValue(WithType, null, each ComposeText(_), Replacer.ReplaceValue, {TargetCol})
    else
      Table.ReplaceValue(WithType, each Record.Field(_, TargetCol), each ComposeText(_), Replacer.ReplaceValue, {TargetCol})
in
  Result,
    #"Cpy Invoice# -> *Invoice Number" = /* TEMPLATE: Fill/overwrite a column from ANOTHER query using a flat join (collision-safe)

   WHAT IT DOES
   - Renames right-side (OtherQuery) key columns so they don't collide with left-side names.
   - Optionally renames the right-side source column to a temp name.
   - Joins, fills/overwrites the target, then removes the temp columns.

   HOW TO USE
   - Edit only the CONFIG block.
   - KeysThis/KeysOther can be single or multiple keys (orders must match).
   - Set ReplaceNullsOnly = true to only fill blanks; false to overwrite all.
*/
/* TEMPLATE: Fill/overwrite a column from ANOTHER query using a flat join (collision-safe)

   WHAT IT DOES
   - Renames right-side (OtherQuery) key columns so they don't collide with left-side names.
   - Optionally renames the right-side source column to a temp name.
   - Joins, fills/overwrites the target, then removes the temp columns.

   HOW TO USE
   - Edit only the CONFIG block.
   - KeysThis/KeysOther can be single or multiple keys (orders must match).
   - Set ReplaceNullsOnly = true to only fill blanks; false to overwrite all.
*/
/* TEMPLATE: Fill/overwrite a column from ANOTHER query using a flat join (collision-safe)

   WHAT IT DOES
   - Renames right-side (OtherQuery) key columns so they don't collide with left-side names.
   - Optionally renames the right-side source column to a temp name.
   - Joins, fills/overwrites the target, then removes the temp columns.

   HOW TO USE
   - Edit only the CONFIG block.
   - KeysThis/KeysOther can be single or multiple keys (orders must match).
   - Set ReplaceNullsOnly = true to only fill blanks; false to overwrite all.
*/
/* TEMPLATE: Fill/overwrite a column from ANOTHER query using a flat join (collision-safe)

   WHAT IT DOES
   - Renames right-side (OtherQuery) key columns so they don't collide with left-side names.
   - Optionally renames the right-side source column to a temp name.
   - Joins, fills/overwrites the target, then removes the temp columns.

   HOW TO USE
   - Edit only the CONFIG block.
   - KeysThis/KeysOther can be single or multiple keys (orders must match).
   - Set ReplaceNullsOnly = true to only fill blanks; false to overwrite all.
*/
/* TEMPLATE: Fill/overwrite a column from ANOTHER query using a flat join (collision-safe)

   WHAT IT DOES
   - Renames right-side (OtherQuery) key columns so they don't collide with left-side names.
   - Optionally renames the right-side source column to a temp name.
   - Joins, fills/overwrites the target, then removes the temp columns.

   HOW TO USE
   - Edit only the CONFIG block.
   - KeysThis/KeysOther can be single or multiple keys (orders must match).
   - Set ReplaceNullsOnly = true to only fill blanks; false to overwrite all.
*/
/* ==============================================================
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
  ThisTable         = #"Set Import Set -> Fixed + Date",   // your current step/table
  OtherQuery        = #"Matched",                          // the other query (its NAME)
  KeysThis          = {"Index"},                           // key(s) in ThisTable (order matters)
  KeysOther         = {"Index"},                           // corresponding key(s) in OtherQuery (same order/length)
  TargetColThis     = "*Invoice Number",                   // column to fill/overwrite in ThisTable
  SourceColOther    = "Invoice #",                   // column to copy from in OtherQuery
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
    #"Cpy Debit Amt -> Invoice Amount" = /* ==============================================================
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
  ThisTable         = #"Cpy Invoice# -> *Invoice Number",   // your current step/table
  OtherQuery        = #"Matched",                          // the other query (its NAME)
  KeysThis          = {"Index"},                           // key(s) in ThisTable (order matters)
  KeysOther         = {"Index"},                           // corresponding key(s) in OtherQuery (same order/length)
  TargetColThis     = "*Invoice Amount",                   // column to fill/overwrite in ThisTable
  SourceColOther    = "Debit Amt",                   // column to copy from in OtherQuery
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
  ThisTable         = #"Cpy Debit Amt -> Invoice Amount",   // your current step/table
  OtherQuery        = #"Matched",                          // the other query (its NAME)
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
    #"Cpy/Fill Payment\nMethod -> Payment" = /* ==============================================================
   TEMPLATE: If last token (from another query's column) has NO digits,
             write a value into Target; otherwise leave Target as-is.
   --------------------------------------------------------------
   WHAT THIS DOES
   - Joins your table (ThisTable) with another query (OtherQuery) by keys.
   - From OtherQuery[SourceColOther], trims & splits on whitespace and
     extracts the LAST token per row.
   - If that token contains ANY digit 0–9 → do nothing.
     Else → write ValueIfNoDigits into TargetColThis.
   - Optionally only fill when Target is null/blank (default true).
   - Keeps Target column position (in-place), and cleans temp columns.

   HOW TO USE
   1) Edit the CONFIG block only.
   2) Make sure KeysThis/KeysOther match (same order/length and types).
   3) Set SourceColOther to the column in OtherQuery you want to inspect.
   ============================================================== */

/* ==============================================================
   TEMPLATE: If last token (from another query's column) has NO digits,
             write a value into Target; otherwise leave Target as-is.
   --------------------------------------------------------------
   WHAT THIS DOES
   - Joins your table (ThisTable) with another query (OtherQuery) by keys.
   - From OtherQuery[SourceColOther], trims & splits on whitespace and
     extracts the LAST token per row.
   - If that token contains ANY digit 0–9 → do nothing.
     Else → write ValueIfNoDigits into TargetColThis.
   - Optionally only fill when Target is null/blank (default true).
   - Keeps Target column position (in-place), and cleans temp columns.

   HOW TO USE
   1) Edit the CONFIG block only.
   2) Make sure KeysThis/KeysOther match (same order/length and types).
   3) Set SourceColOther to the column in OtherQuery you want to inspect.
   ============================================================== */

/* ==============================================================
   TEMPLATE: If last token (from another query's column) has NO digits,
             write a value into Target; otherwise leave Target as-is.
   --------------------------------------------------------------
   WHAT THIS DOES
   - Joins your table (ThisTable) with another query (OtherQuery) by keys.
   - From OtherQuery[SourceColOther], trims & splits on whitespace and
     extracts the LAST token per row.
   - If that token contains ANY digit 0–9 → do nothing.
     Else → write ValueIfNoDigits into TargetColThis.
   - Optionally only fill when Target is null/blank (default true).
   - Keeps Target column position (in-place), and cleans temp columns.

   HOW TO USE
   1) Edit the CONFIG block only.
   2) Make sure KeysThis/KeysOther match (same order/length and types).
   3) Set SourceColOther to the column in OtherQuery you want to inspect.
   ============================================================== */

/* ==============================================================
   TEMPLATE: If last token (from another query's column) has NO digits,
             write a value into Target; otherwise leave Target as-is.
   --------------------------------------------------------------
   WHAT THIS DOES
   - Joins your table (ThisTable) with another query (OtherQuery) by keys.
   - From OtherQuery[SourceColOther], trims & splits on whitespace and
     extracts the LAST token per row.
   - If that token contains ANY digit 0–9 → do nothing.
     Else → write ValueIfNoDigits into TargetColThis.
   - Optionally only fill when Target is null/blank (default true).
   - Keeps Target column position (in-place), and cleans temp columns.

   HOW TO USE
   1) Edit the CONFIG block only.
   2) Make sure KeysThis/KeysOther match (same order/length and types).
   3) Set SourceColOther to the column in OtherQuery you want to inspect.
   ============================================================== */

/* ==============================================================
   TEMPLATE: If last token (from another query's column) has NO digits,
             write a value into Target; otherwise leave Target as-is.
   --------------------------------------------------------------
   WHAT THIS DOES
   - Joins your table (ThisTable) with another query (OtherQuery) by keys.
   - From OtherQuery[SourceColOther], trims & splits on whitespace and
     extracts the LAST token per row.
   - If that token contains ANY digit 0–9 → do nothing.
     Else → write ValueIfNoDigits into TargetColThis.
   - Optionally only fill when Target is null/blank (default true).
   - Keeps Target column position (in-place), and cleans temp columns.

   HOW TO USE
   1) Edit the CONFIG block only.
   2) Make sure KeysThis/KeysOther match (same order/length and types).
   3) Set SourceColOther to the column in OtherQuery you want to inspect.
   ============================================================== */

/* ==============================================================
   TEMPLATE: If last token (from another query's column) has NO digits,
             write a value into Target; otherwise leave Target as-is.
   --------------------------------------------------------------
   WHAT THIS DOES
   - Joins your table (ThisTable) with another query (OtherQuery) by keys.
   - From OtherQuery[SourceColOther], trims & splits on whitespace and
     extracts the LAST token per row.
   - If that token contains ANY digit 0–9 → do nothing.
     Else → write ValueIfNoDigits into TargetColThis.
   - Optionally only fill when Target is null/blank (default true).
   - Keeps Target column position (in-place), and cleans temp columns.

   HOW TO USE
   1) Edit the CONFIG block only.
   2) Make sure KeysThis/KeysOther match (same order/length and types).
   3) Set SourceColOther to the column in OtherQuery you want to inspect.
   ============================================================== */

/* ==============================================================
   TEMPLATE: Join to another query → inspect LAST token from a column
             If LAST token HAS any digits → write a CUSTOM value
             Else (NO digits) → write the token itself
             (Local, in-place update; only fill blanks by default)

   WHAT THIS DOES
   - Left side (ThisTable): your current query step.
   - Right side (OtherQuery): another query (its NAME; resolves to its final step).
   - Joins left↔right using KeysThis / KeysOther (one or more columns; order must match).
   - From right column [SourceColOther], it TRIMS, splits on whitespace, and takes the LAST token.
   - Decision:
       • If that token contains ANY digit (0–9) → write ValueIfHasDigits into TargetColThis.
       • If that token has NO digits → write the token itself into TargetColThis.
   - Option: only fill when Target is blank/null (default true).
   - Safety:
       • Checks the right-side source column exists (clear error if not).
       • Avoids duplicate column name collisions during the join.
       • Keeps Target column in its original position (in-place swap).
       • Cleans up temporary columns after writing.

   HOW TO USE
   1) Edit ONLY the CONFIG block below (names are case-sensitive).
   2) Make sure KeysThis/KeysOther list the same number of columns in the same order.
   3) Make sure join key TYPES match (Text vs Number). If not, retype earlier or add a type-fix step.
   4) Press Enter. If errors appear, read the error message; it points to the exact missing/incorrect piece.
   ============================================================== */

/* ==============================================================
   TEMPLATE: Write LAST token (from another query's column) when it HAS digits;
             otherwise write a custom fallback value. (local, in-place)
   --------------------------------------------------------------
   WHAT THIS DOES
   - Joins your table (ThisTable) to another query (OtherQuery) on keys.
   - From OtherQuery[SourceColOther], TRIMs and splits on whitespace, then
     extracts the LAST token per row.
   - Decision:
       * If that token contains ANY digit 0–9 → write the token to Target.
       * Else → write ValueIfNoDigits to Target.
   - Optionally only fill when Target is null/blank (default true).
   - Keeps Target column position (in-place) and cleans temp columns.
   - Collision-safe on joins (renames right-side keys).

   HOW TO USE
   1) Edit the CONFIG block only.
   2) KeysThis and KeysOther must have the same length and order; types should match.
   3) Set SourceColOther to the column in OtherQuery that provides the text.
   ============================================================== */

/* ==============================================================
   TEMPLATE: If LAST token (from another query's column) HAS digits,
             write the WHOLE source cell to Target; otherwise write a fallback.
   --------------------------------------------------------------
   WHAT THIS DOES
   - Joins your table (ThisTable) with another query (OtherQuery) on keys.
   - From OtherQuery[SourceColOther]:
       * TRIM ends
       * Split on whitespace
       * Take the LAST token
   - Decision:
       * If LAST token contains ANY digit 0–9 → write the WHOLE TRIMMED SOURCE CELL to Target.
       * Else → write ValueIfNoDigits to Target.
   - Optional: only fill when Target is null/blank (default true).
   - Keeps Target column position (in-place). Cleans temp columns.
   ============================================================== */

let
  // =========================
  // ========= CONFIG ========
  // =========================
  ThisTable          = #"Cpy Description -> Description",   // your current step/table
  OtherQuery         = #"Matched",                          // the other query's NAME (its final step)

  // Join keys (single or multiple). Order must match between left/right; types should match too.
  KeysThis           = {"Index"},
  KeysOther          = {"Index"},

  // Columns
  TargetColThis      = "Payment Method",                    // column to write into (created if missing)
  SourceColOther     = "Payment",                           // right-side column to inspect

  // Behavior
  ValueIfNoDigits    = "ACH CLEARING",                      // value to write when LAST token has NO digits
  ReplaceNullsOnly   = true,                                // true = fill only when Target is null/blank; false = overwrite
  TreatBlankAsNull   = true,                                // treat ""/whitespace as blank for the null-only behavior

  // Misc / safety
  TargetType         = type text,                           // final type for Target column
  FromTokenNameBase  = "__FromToken",                       // temp col for LAST token (auto-uniqued if needed)
  FromSrcNameBase    = "__FromSrc",                         // temp col for WHOLE trimmed source (auto-uniqued)

  // ===============================
  // ===== IMPLEMENTATION (no edits)
  // ===============================
  // Keep Target column in place if it already existed
  OrigCols        = Table.ColumnNames(ThisTable),
  TargetExisted   = List.Contains(OrigCols, TargetColThis),

  // Ensure Target exists and is text-typed (or your chosen TargetType)
  EnsureTarget    = if TargetExisted then ThisTable else Table.AddColumn(ThisTable, TargetColThis, each null),
  WithType        = if TargetType <> null then Table.TransformColumnTypes(EnsureTarget, {{TargetColThis, TargetType}}) else EnsureTarget,

  // Prepare safe temp names that won't collide with left columns
  FromTokenName   = if List.Contains(OrigCols, FromTokenNameBase) then FromTokenNameBase & "_r" else FromTokenNameBase,
  FromSrcName     = if List.Contains(OrigCols, FromSrcNameBase)   then FromSrcNameBase   & "_r" else FromSrcNameBase,

  // --- RIGHT SIDE: verify source column exists, slim to keys+source, compute helpers ---
  RightCols0      = Table.ColumnNames(OtherQuery),
  _CheckSource    = if not List.Contains(RightCols0, SourceColOther) then
                      error Error.Record(
                        "MissingSourceColumn",
                        "Right-side column '" & SourceColOther & "' was not found in the other query.",
                        [ RightColumns = RightCols0 ]
                      )
                    else null,

  // Keep only keys + the source column
  OtherSlim       = Table.SelectColumns(OtherQuery, List.Distinct(KeysOther & {SourceColOther}), MissingField.Ignore),

  // Helper: TRIM ends
  TrimText = (txt as nullable any) as nullable text =>
    let s = if txt = null then null else Text.From(txt)
    in  if s = null then null else Text.Trim(s),

  // Helper: LAST whitespace-separated token
  ExtractLastToken = (txt as nullable any) as nullable text =>
    let
      t      = TrimText(txt),
      parts0 = if t = null then {} else Text.SplitAny(t, " " & "#(tab)" & "#(cr)" & "#(lf)"),
      parts  = List.Select(parts0, each _ <> ""),
      tok    = if List.Count(parts) = 0 then null else parts{List.Count(parts)-1}
    in
      tok,

  // Add both the WHOLE TRIMMED SOURCE and the LAST TOKEN as helper columns
  WithSrc  = Table.AddColumn(OtherSlim, "__SrcTrim",   each TrimText(Record.Field(_, SourceColOther)), type text),
  WithTok  = Table.AddColumn(WithSrc,   "__LastToken", each ExtractLastToken(Record.Field(_, SourceColOther)), type text),

  // Collision-safe: rename right-side keys so they don't duplicate left names
  KeyRenamePairs   = List.Transform(KeysOther, each {_, "__rK_" & _}),
  OtherKeysRenamed = Table.RenameColumns(WithTok, KeyRenamePairs, MissingField.Ignore),
  KeysOtherRenamed = List.Transform(KeysOther, each "__rK_" & _),

  // Rename helper columns to known safe names we will reference after the join
  OtherPrepared  = Table.RenameColumns(OtherKeysRenamed, {{"__LastToken", FromTokenName}, {"__SrcTrim", FromSrcName}}),

  // --- JOIN ---
  Joined0        = Table.Join(WithType, KeysThis, OtherPrepared, KeysOtherRenamed, JoinKind.LeftOuter),

  // Ensure Target exists on the joined table (if it didn't before)
  Joined         = if List.Contains(Table.ColumnNames(Joined0), TargetColThis)
                   then Joined0
                   else Table.AddColumn(Joined0, TargetColThis, each null),

  // --- Decision logic ---
  Digits         = {"0","1","2","3","4","5","6","7","8","9"},
  HasAnyDigit    = (s as nullable text) as logical =>
                     if s = null then false else List.ContainsAny(Text.ToList(s), Digits),

  IsBlank        = (v as any) as logical =>
                     (v = null) or (TreatBlankAsNull and Value.Is(v, type text) and Text.Trim(v) = ""),

  WithNew        =
    Table.AddColumn(
      Joined,
      "__new",
      each
        let
          cur     = Record.Field(_, TargetColThis),            // current value in Target
          tok     = try Record.Field(_, FromTokenName) otherwise null, // LAST token
          srcAll  = try Record.Field(_, FromSrcName)   otherwise null, // WHOLE trimmed source cell
          cand    = if tok <> null and HasAnyDigit(tok)
                    then srcAll                               // when LAST token HAS digits → write WHOLE source
                    else ValueIfNoDigits,                     // otherwise → fallback
          result  =
            if ReplaceNullsOnly
            then (if IsBlank(cur) and cand <> null then cand else cur)
            else (if cand <> null then cand else cur)
        in
          result,
      TargetType
    ),

  // Swap in-place & clean temp columns (drop right-side key dups + helpers)
  RemovedOld     = Table.RemoveColumns(WithNew, {TargetColThis}),
  Renamed        = Table.RenameColumns(RemovedOld, {"__new", TargetColThis}),
  DropCols       = List.Distinct(KeysOtherRenamed & {FromTokenName, FromSrcName, SourceColOther}),
  Clean          = Table.RemoveColumns(Renamed, DropCols),

  // Put columns back where they were (if target existed originally)
  Reordered      = if TargetExisted then Table.ReorderColumns(Clean, OrigCols, MissingField.Ignore) else Clean
in
  Reordered,
    #"Detect Types" = Table.TransformColumnTypes(#"Cpy/Fill Payment\nMethod -> Payment",{{"*Invoice Date", type date}, {"*Invoice Amount", type number}}),
    #"Delete extra rows" = /* TEMPLATE: Delete rows when ANY/ALL of selected columns are empty
   HOW TO USE:
   1) Edit the CONFIG block only.
   2) Set DeleteMode to "Any" or "All".
   3) Choose what counts as "empty" (nulls, blank text, zero numbers).
*/
let
  // =========================
  // ========= CONFIG ========
  // =========================
  TableIn                   = #"Detect Types",   // prior step in THIS query
  ColumnsToCheck            = {"**Supplier Name", "Description"},  // columns to test for emptiness
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