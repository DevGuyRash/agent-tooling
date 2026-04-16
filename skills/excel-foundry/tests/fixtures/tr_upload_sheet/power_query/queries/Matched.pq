let
    Source = Excel.Workbook(File.Contents("C:\Users\E135328\Documents\Da Work\2025\11 - November\05 - Wednesday\2025-11-05_ak_preauths_alteryx.xlsx"), null, true),
    Matched_Sheet = Source{[Item="Matched",Kind="Sheet"]}[Data],
    #"Promoted Headers" = Table.PromoteHeaders(Matched_Sheet, [PromoteAllScalars=true]),
    #"Added Index" = Table.AddIndexColumn(#"Promoted Headers", "Index", 0, 1, Int64.Type),
    #"Fill Invoice #'s" = /* TEMPLATE: Fill a column with Date (+ optional sequence BY KEY), IN-PLACE, using SAFE TEXT KEYS
   - Per-key running index in original row order (non-contiguous duplicates handled).
   - Groups on derived text keys so mixed types like "CV5354" won't cause number conversion errors.
   - Fills only null/blank by default; can overwrite all.
   - Keeps target column's original position if it already existed.
   - EDIT ONLY THE CONFIG BLOCK.
*/
/* TEMPLATE: Fill a column with Date (+ optional sequence BY KEY), IN-PLACE, using SAFE TEXT KEYS
   - Per-key running index in original row order (non-contiguous duplicates handled).
   - Groups on derived text keys so mixed types like "CV5354" won't cause number conversion errors.
   - Fills only null/blank by default; can overwrite all.
   - Keeps target column's original position if it already existed.
   - EDIT ONLY THE CONFIG BLOCK.
*/
/* TEMPLATE: Fill a column with Date (+ optional sequence BY KEY), IN-PLACE, using SAFE TEXT KEYS
   - Per-key running index in original row order (non-contiguous duplicates handled).
   - Groups on derived text keys so mixed types like "CV5354" won't cause number conversion errors.
   - Fills only null/blank by default; can overwrite all.
   - Keeps target column's original position if it already existed.
   - EDIT ONLY THE CONFIG BLOCK.
*/
/* TEMPLATE: Fill a column with Date (+ optional sequence BY KEY), IN-PLACE, using SAFE TEXT KEYS
   - Per-key running index in original row order (non-contiguous duplicates handled).
   - Groups on derived text keys so mixed types like "CV5354" won't cause number conversion errors.
   - Fills only null/blank by default; can overwrite all.
   - Keeps target column's original position if it already existed.
   - EDIT ONLY THE CONFIG BLOCK.
*/
/* TEMPLATE: Fill a column with Date (+ optional sequence BY KEY), IN-PLACE, with SAFE KEY TYPES */
/* TEMPLATE: Fill a column with Date (+ optional sequence BY KEY), IN-PLACE, with SAFE KEY TYPES */
/* TEMPLATE: Fill a column with Date (+ optional sequence BY KEY), IN-PLACE, with SAFE KEY TYPES
     + Prefix/Suffix support (non-breaking if left empty)
*/
/* TEMPLATE: Fill a column with Date (+ optional sequence BY KEY), IN-PLACE, with SAFE KEY TYPES
     + Prefix/Suffix support (non-breaking if left empty)
*/
let
  // ===== CONFIG =====
  TableIn                = #"Added Index",
  TargetCol              = "Invoice #",
  ReplaceNullsOnly       = true,
  TreatBlankTextAsNull   = true,

  DupKeys                = {"VendorId"},
  RequireAllKeys         = true,
  SortWithinKey          = null,

  AppendSeparator        = "-",
  AppendStart            = 1,
  AppendIncrement        = 1,

  // --- DATE SOURCE & FORMAT ---
  // Default now uses a column called "As-Of-Time" (customizable).
  // To mimic the old behavior (Today - 1): set BaseDateMode = "Today" and DaysOffset = -1.
  BaseDateMode           = "Column",         // "Column" | "Today" | "Fixed"
  BaseDateCol            = "As-Of Date",
  BaseDateFixed          = #date(2025, 1, 1),
  YearsOffset            = 0,
  MonthsOffset           = 0,
  DaysOffset             = 0,                // no offset by default when using a column
  DateFormat             = "MMddyyyy",
  DateCulture            = null,

  TargetType             = type text,
  SafeKeyPrefix          = "__k_",
  NormalizeKeyTrim       = true,
  NormalizeKeyCase       = false,

  // --- Affixes (set to "" or null to disable; non-breaking) ---
  PrefixText             = "",               // e.g., "PRE-"
  SuffixText             = "-TR",            // e.g., "-A"
  AddPrefixOnlyIfBase    = true,             // omit prefix if proposed base is blank
  AddSuffixOnlyIfBase    = true,             // omit suffix if proposed base is blank

  // ===== IMPLEMENTATION =====
  OrigCols        = Table.ColumnNames(TableIn),
  TargetExisted   = List.Contains(OrigCols, TargetCol),

  EnsureTarget    = if TargetExisted then TableIn else Table.AddColumn(TableIn, TargetCol, each null),
  WithType        = if TargetType <> null then Table.TransformColumnTypes(EnsureTarget, {{TargetCol, TargetType}}) else EnsureTarget,

  // *** EARLY FIX: stop number parsing on dup keys ***
  ExistingKeys     = List.Intersect({DupKeys, Table.ColumnNames(WithType)}),
  CoerceKeysToText = Table.TransformColumnTypes(WithType, List.Transform(ExistingKeys, each {_, type text})),

  AllCols0        = Table.ColumnNames(CoerceKeysToText),
  MissingKeys     = List.Difference(DupKeys, AllCols0),
  _CheckKeys      = if RequireAllKeys and List.Count(MissingKeys) > 0
                      then error Error.Record("MissingKeys", "Missing key column(s) for grouping: " & Text.Combine(MissingKeys, ", "), [Missing = MissingKeys])
                      else null,

  WithOrd         = Table.AddIndexColumn(CoerceKeysToText, "__ord", 0, 1, Int64.Type),

  // Build SAFE text keys (still useful for trim/upper & to avoid name collisions)
  MkSafeName      = (nm as text) as text =>
                      let base = SafeKeyPrefix & nm
                      in if List.Contains(Table.ColumnNames(WithOrd), base) then base & "_r" else base,

  KeysForGroup    = DupKeys,
  SafeKeyNames    = List.Transform(KeysForGroup, each MkSafeName(_)),

  AddSafeKeys =
    (tbl as table, origKeys as list, safeNames as list) as table =>
      let
        pairs  = List.Zip({origKeys, safeNames}),
        added  = List.Accumulate(
                  pairs,
                  tbl,
                  (state, p) =>
                    let
                      orig = p{0}, safe = p{1}
                    in
                      Table.AddColumn(
                        state,
                        safe,
                        each
                          let
                            v0 = try Record.Field(_, orig) otherwise null,
                            t  = if v0 = null then null else try Text.From(v0) otherwise null,
                            t1 = if t = null then null else if NormalizeKeyTrim then Text.Trim(t) else t,
                            t2 = if t1 = null then null else if NormalizeKeyCase then Text.Upper(t1) else t1
                          in
                            t2,
                        type text
                      )
                )
      in
        added,

  WithKeys        = AddSafeKeys(WithOrd, KeysForGroup, SafeKeyNames),

  // --- Date builder (moved up so we can build a per-row date key BEFORE grouping)
  GetDateText = (r as record) as nullable text =>
    let
      baseRaw  =
        if BaseDateMode = "Column" then try Record.Field(r, BaseDateCol) otherwise null
        else if BaseDateMode = "Today" then Date.From(DateTime.LocalNow())
        else if BaseDateMode = "Fixed" then BaseDateFixed
        else null,
      baseDate = try Date.From(baseRaw) otherwise null,
      afterY   = if baseDate <> null then Date.AddYears(baseDate,  YearsOffset)  else null,
      afterM   = if afterY   <> null then Date.AddMonths(afterY,   MonthsOffset) else null,
      afterD   = if afterM   <> null then Date.AddDays(afterM,     DaysOffset)   else null,
      dText    = if afterD = null then null
                 else if DateCulture = null then Date.ToText(afterD, DateFormat)
                 else Date.ToText(afterD, DateFormat, DateCulture)
    in dText,

  // --- NEW: Per-row date key to isolate counting PER VendorId PER Date
  WithDateKey     = Table.AddColumn(WithKeys, "__dateKey", each GetDateText(_), type text),

  // Group by vendor-safe keys AND __dateKey (so counting restarts for each date)
  KeysToGroup     = SafeKeyNames & {"__dateKey"},

  Grouped =
    Table.Group(
      WithDateKey,
      KeysToGroup,
      {
        { "__g",
          (t as table) =>
            let
              tSorted = if SortWithinKey is null
                        then Table.Sort(t, {{"__ord", Order.Ascending}})
                        else Table.Sort(t, SortWithinKey & {{"__ord", Order.Ascending}}),
              withRN  = Table.AddIndexColumn(tSorted, "__rn", 1, 1, Int64.Type)
            in withRN,
          type table
        }
      }
    ),

  AllColsAfter   = Table.ColumnNames(WithDateKey),
  // IMPORTANT: exclude ALL group keys (vendor-safe + __dateKey) from expansion to avoid duplicates
  NonKeyCols     = List.Distinct(List.RemoveItems(AllColsAfter, KeysToGroup) & {"__rn"}),
  Expanded       = Table.ExpandTableColumn(Grouped, "__g", NonKeyCols, NonKeyCols),

  // Drop only the vendor-safe keys here; keep __dateKey for downstream use, drop later
  DroppedSafe    = Table.RemoveColumns(Expanded, SafeKeyNames),
  Restored       = Table.Sort(DroppedSafe, {{"__ord", Order.Ascending}}),

  // --- Existing proposal logic → now uses the precomputed __dateKey
  ProposedCore =
    Table.AddColumn(
      Restored,
      "__proposedCore",
      each
        let
          dateText   = try Record.Field(_, "__dateKey") otherwise null,
          rn         = try Record.Field(_, "__rn") otherwise null,
          needAppend = rn <> null and rn >= 2,
          seq        = if needAppend then AppendStart + (Number.From(rn) - 2) * AppendIncrement else null,
          // SAFETY: do not attempt to append sequence when dateText is null
          outText    =
            if dateText = null then null
            else if not needAppend then dateText
            else Text.Combine({dateText, Text.From(seq)}, AppendSeparator)
        in outText,
      type text
    ),

  // --- Affix wrapper (unchanged logic, isolated)
  ComposeAffix = (base as nullable text) as nullable text =>
    let
      b        = base,
      // local blank check (kept here so we don't move your IsBlank definition)
      isBlankB = (b = null) or (TreatBlankTextAsNull and ((try Text.Trim(b) otherwise "") = "")),
      pre      = if PrefixText = null or PrefixText = "" then "" else if AddPrefixOnlyIfBase and isBlankB then "" else PrefixText,
      suf      = if SuffixText = null or SuffixText = "" then "" else if AddSuffixOnlyIfBase and isBlankB then "" else SuffixText,
      out      = if b = null then null else pre & b & suf
    in out,

  // Apply affixes → __proposed (downstream still looks for __proposed)
  Proposed =
    Table.AddColumn(
      ProposedCore,
      "__proposed",
      each ComposeAffix(try Record.Field(_, "__proposedCore") otherwise null),
      type text
    ),

  // Fill logic (unchanged)
  IsBlank = (v as any) as logical =>
    (v = null) or (TreatBlankTextAsNull and Value.Is(v, type text) and Text.Trim(v) = ""),

  WithNewTarget =
    Table.AddColumn(
      Proposed,
      "__new",
      each if ReplaceNullsOnly
           then (let cur = Record.Field(_, TargetCol) in if IsBlank(cur) then Record.Field(_, "__proposed") else cur)
           else Record.Field(_, "__proposed"),
      TargetType
    ),

  RemovedOld     = Table.RemoveColumns(WithNewTarget, {TargetCol}),
  Renamed        = Table.RenameColumns(RemovedOld, {"__new", TargetCol}),
  // Drop work columns, including the NEW __dateKey
  Cleaned        = Table.RemoveColumns(Renamed, {"__ord","__rn","__proposed","__proposedCore","__dateKey"}),
  Reordered      = if TargetExisted
                   then Table.ReorderColumns(Cleaned, OrigCols, MissingField.Ignore)
                   else Cleaned
in
  Reordered,
    #"Rpl VIN-STOCK -> Vin Number" = /* TEMPLATE: Replace a token in Target with the LAST whitespace-token from Source (local, in-place)
   Use-case example (edit in CONFIG):
     - SearchText    = "VIN-STOCK"
     - TargetCol     = "Description"
     - SourceCol     = "Clearing"
*/
/* TEMPLATE: Replace a token in Target with the LAST whitespace-token from Source (local, in-place)
   Use-case example (edit in CONFIG):
     - SearchText    = "VIN-STOCK"
     - TargetCol     = "Description"
     - SourceCol     = "Clearing"
*/
/* TEMPLATE: Replace a token in Target with the LAST whitespace-token from Source (local, in-place)
   Use-case example (edit in CONFIG):
     - SearchText    = "VIN-STOCK"
     - TargetCol     = "Description"
     - SourceCol     = "Clearing"
*/
/* TEMPLATE: Replace a token in Target with the LAST whitespace-token from Source (local, in-place)
   Use-case example (edit in CONFIG):
     - SearchText    = "VIN-STOCK"
     - TargetCol     = "Description"
     - SourceCol     = "Clearing"
*/
let
  // =========================
  // ========= CONFIG ========
  // =========================
  TableIn              = #"Fill Invoice #'s",   // prior step in THIS query
  TargetCol            = "Description",     // column to update (created if missing)
  SourceCol            = "Clearing",        // column to extract last token from
  SearchText           = "VIN-STOCK",       // substring to replace in Target
  IncludeNullBlanks    = false,             // true = if Target is blank/null, fill entire cell with token
  TreatBlankAsNull     = true,              // trims and treats "" / whitespace-only as blank for the fill behavior
  TargetType           = type text,         // final type for Target (text recommended)
  // Note: Text.Replace / Text.Contains are case-sensitive. If your data varies in case, normalize first.

  // ===============================
  // ===== IMPLEMENTATION (no edits)
  // ===============================

  // remember original columns to keep Target in place
  OrigCols          = Table.ColumnNames(TableIn),
  TargetExisted     = List.Contains(OrigCols, TargetCol),

  // ensure Target exists and is text-typed (or whatever TargetType you want)
  EnsureTarget      = if TargetExisted then TableIn else Table.AddColumn(TableIn, TargetCol, each null),
  WithType          = if TargetType <> null then Table.TransformColumnTypes(EnsureTarget, {{TargetCol, TargetType}}) else EnsureTarget,

  // helper: get last whitespace-separated token from SourceCol
  // - trims ends, splits on space/tab/CR/LF, removes empties, returns last or null
  ExtractLastToken  = (r as record) as nullable text =>
    let
      raw     = Record.FieldOrDefault(r, SourceCol, null),
      txt     = if raw = null then null else Text.From(raw),
      trimmed = if txt = null then null else Text.Trim(txt),
      parts0  = if trimmed = null then {} else Text.SplitAny(trimmed, " " & "#(tab)" & "#(cr)" & "#(lf)"),
      parts   = List.Select(parts0, each _ <> ""),
      token   = if List.Count(parts) = 0 then null else parts{List.Count(parts)-1}
    in
      token,

  // build the new Target values row-wise
  WithNew =
    Table.AddColumn(
      WithType,
      "__new",
      each
        let
          tgt0        = Record.Field(_, TargetCol),
          tgtText     = if tgt0 = null then null else Text.From(tgt0),
          tok         = ExtractLastToken(_),
          hasSearch   = if tgtText = null then false else Text.Contains(tgtText, SearchText),
          // replace occurrences of SearchText with token (if token exists)
          replaced    = if hasSearch and tok <> null then Text.Replace(tgtText, SearchText, tok) else tgtText,
          // optionally fill blanks with token when no search match
          isBlank     = (tgtText = null) or (TreatBlankAsNull and tgtText <> null and Text.Trim(tgtText) = ""),
          filledBlank = if (not hasSearch) and IncludeNullBlanks and isBlank and (tok <> null) then tok else replaced
        in
          filledBlank,
      TargetType
    ),

  // swap in-place & clean helpers
  RemovedOld  = Table.RemoveColumns(WithNew, {TargetCol}),
  Renamed     = Table.RenameColumns(RemovedOld, {"__new", TargetCol}),
  Reordered   = if TargetExisted then Table.ReorderColumns(Renamed, OrigCols, MissingField.Ignore) else Renamed
in
  Reordered,
    #"Detect Types" = Table.TransformColumnTypes(#"Rpl VIN-STOCK -> Vin Number",{{"As-Of Date", type date}, {"As-Of-Time", type time}})
in
    #"Detect Types"