Option Explicit

'=========================================================================
' PATCH NOTES
'   Merge these replacements into macros/modules/modAPSync.vba.
'
'   Key behavior changes:
'     - fast edit mode is enabled BEFORE pastes (via sheet activate event)
'     - native table auto-expand and line-formula auto-fill stay enabled during editing
'     - tbl_record_lines becomes grow-only during editing (no auto-shrink)
'     - managed formula columns are hard-coded (no .HasFormula guessing)
'     - large pastes queue record sync and formatting work for deferred flush
'     - line-formula refill is used only as a fallback when native autofill misses rows
'==========================================================================

'============================
' REPLACE / ADD CONSTANTS
'============================
Private Const SH_RECORDS As String = "DATA_RECORDS"
Private Const SH_LINES    As String = "DATA_RECORD_LINES"

Private Const TBL_RECORDS As String = "tbl_records"
Private Const TBL_LINES    As String = "tbl_record_lines"

Private Const LINES_BUFFER_ROWS As Long = 25
Private Const LINES_GROW_CHUNK As Long = 250
Private Const COL_LINE_NUMBER As String = "Line Number"
Private Const COL_LINE_KEY As String = "zzLineKey"
Private Const COL_RECORD_KEY As String = "zzRecordKey"
Private Const SYNC_DEBOUNCE_MS As Long = 250
Private Const STATUS_SYNC_PENDING As String = "AP sync pending..."
Private Const STATUS_SYNC_RUNNING As String = "AP sync running..."
Private Const STATUS_SYNC_FAST_EDIT As String = "AP edit mode: fast"
Private Const COL_INV_ID_FORMULA As String = "*Record ID"
Private Const COL_INV_NUMBER_FORMULA As String = "*Record Number"
Private Const COL_ATTR6_FORMULA As String = "Attribute 6"
Private Const COL_PROJECT_FORMULA As String = "Project Number"

Private mSyncPending As Boolean
Private mSyncInFlight As Boolean
Private mSyncRunScheduled As Boolean
Private mScheduledRunAt As Date
Private mPendingBottomRow As Long
Private mPendingTopRow As Long
Private mPendingFirstCol As Long
Private mPendingLastCol As Long
Private mPendingProtectRows As Boolean
Private mPendingRunRecordSync As Boolean
Private mPendingSilent As Boolean

Private mDeferredLineFormulasPending As Boolean
Private mDeferredLineCfPending As Boolean
Private mDeferredRecordSyncPending As Boolean
Private mFlushDeferredAfterExitPending As Boolean
Private mSavedLinesEnableCalculation As Variant
Private mSavedRecordsEnableCalculation As Variant
Private mHaveSavedLinesEnableCalculation As Boolean
Private mHaveSavedRecordsEnableCalculation As Boolean
Private mEditPerfModeEnabled As Boolean
Private mSavedAutoFillFormulasInLists As Variant
Private mSavedAutoExpandListRange As Variant
Private mSavedLineCfCalcEnabled As Variant
Private mHaveSavedAutoFill As Boolean
Private mHaveSavedAutoExpand As Boolean
Private mHaveSavedLineCf As Boolean
Private mRandomSeeded As Boolean
Private mLastKnownLinesTableRows As Long

'============================
' REPLACE AP_QueueSyncAll_WithTarget
'============================
Public Sub AP_SyncRecordsTable(Optional ByVal Silent As Boolean = True, _
                                Optional ByVal SkipLineSync As Boolean = False, _
                                Optional ByVal ManageAppState As Boolean = True)

    Dim prevEvents As Boolean, prevScreen As Boolean
    Dim prevCalc As XlCalculation

    prevEvents = Application.EnableEvents
    prevScreen = Application.ScreenUpdating
    prevCalc = Application.Calculation

    On Error GoTo EH

    If ManageAppState Then
        Application.EnableEvents = False
        Application.ScreenUpdating = False
        Application.Calculation = xlCalculationManual
    End If

    Dim wb As Workbook: Set wb = ThisWorkbook
    Dim wsInv As Worksheet: Set wsInv = wb.Worksheets(SH_RECORDS)
    Dim wsLines As Worksheet: Set wsLines = wb.Worksheets(SH_LINES)

    Dim loInv As ListObject: Set loInv = wsInv.ListObjects(TBL_RECORDS)
    Dim loLines As ListObject: Set loLines = wsLines.ListObjects(TBL_LINES)

    If Not SkipLineSync Then
        SyncRecordLinesCore Silent, 0, 0, 0, 0, False, False
    End If

    EnsureInternalColumn loLines, COL_LINE_KEY
    EnsureInternalColumn loInv, COL_RECORD_KEY

    Dim usedLineRows As Long
    usedLineRows = LastUsedLineNumberRowCount(loLines)

    Dim recordKeys As Collection
    Set recordKeys = RecordKeysFromLines(loLines, usedLineRows)

    Dim oldRows As Long
    oldRows = loInv.ListRows.Count

    Dim firstDataRow As Long
    firstDataRow = loInv.HeaderRowRange.Row + 1

    Dim firstCol As Long, colCount As Long
    firstCol = loInv.Range.Column
    colCount = loInv.Range.Columns.Count

    Dim lcRecordKey As ListColumn
    Set lcRecordKey = GetListColumn(loInv, COL_RECORD_KEY)

    Dim userInputColumns As Collection
    Set userInputColumns = GetUserInputColumns(loInv, True)

    Dim desiredRows As Long
    desiredRows = recordKeys.Count
    If desiredRows < 1 Then desiredRows = 1

    Dim appendedStartRow As Long
    Dim appendedEndRow As Long

    SeedRecordKeysByPosition loInv, lcRecordKey, recordKeys

    If RecordKeysMatchTable(lcRecordKey, recordKeys) Then GoTo FinalizeRecords

    If desiredRows > oldRows Then
        If RecordKeysMatchPrefix(lcRecordKey, recordKeys, oldRows) Then
            ResizeListObjectDataRows loInv, desiredRows
            ApplyListObjectRowFormatsFromPreviousRow loInv, oldRows + 1, desiredRows
            appendedStartRow = oldRows + 1
            appendedEndRow = desiredRows
            Set lcRecordKey = GetListColumn(loInv, COL_RECORD_KEY)

            ApplyRecordKeyAppend loInv, lcRecordKey, userInputColumns, recordKeys, oldRows + 1, desiredRows
            GoTo FinalizeRecords
        End If
    End If

    Dim oldValuesByKey As Object
    Set oldValuesByKey = SnapshotUserInputsByRecordKey(loInv, lcRecordKey, userInputColumns)

    If oldRows <> desiredRows Then
        ResizeListObjectDataRows loInv, desiredRows
        If desiredRows > oldRows Then
            ApplyListObjectRowFormatsFromPreviousRow loInv, oldRows + 1, desiredRows
            appendedStartRow = oldRows + 1
            appendedEndRow = desiredRows
        End If
        Set lcRecordKey = GetListColumn(loInv, COL_RECORD_KEY)
    End If

    ApplyRecordKeyRemap loInv, lcRecordKey, userInputColumns, recordKeys, oldValuesByKey

    If desiredRows < oldRows Then
        ClearOrphanedTableArea wsInv, _
                               firstDataRow + desiredRows, _
                               firstDataRow + oldRows - 1, _
                               firstCol, colCount, False
    End If

FinalizeRecords:
    RecalculateRecordTable loInv
    ApplyRecordNumberBordersFromPreviousRow loInv, appendedStartRow, appendedEndRow

CleanExit:
    If ManageAppState Then
        Application.Calculation = prevCalc
        Application.ScreenUpdating = prevScreen
        Application.EnableEvents = prevEvents
    End If
    Exit Sub

EH:
    If Not Silent Then
        MsgBox "AP_SyncRecordsTable failed: " & Err.Description, vbExclamation
    End If
    Resume CleanExit
End Sub
'Resize tbl_record_lines safely after edits/pastes.
Public Sub AP_SyncRecordLinesTable(Optional ByVal Silent As Boolean = True)
    SyncRecordLinesCore Silent, 0, 0, 0, 0, False, True
End Sub

'Paste-aware entry-point: uses changed range bounds as a temporary floor.
Public Sub AP_SyncRecordLinesTable_WithTarget(Optional ByVal Silent As Boolean = True, _
                                               Optional ByVal changedBottomRow As Long = 0, _
                                               Optional ByVal changedTopRow As Long = 0, _
                                               Optional ByVal changedFirstCol As Long = 0, _
                                               Optional ByVal changedLastCol As Long = 0, _
                                               Optional ByVal protectChangedRows As Boolean = True)
    SyncRecordLinesCore Silent, changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows, True
End Sub

'Single-pass sync wrapper for worksheet events: disables app state once, then runs lines + records sync.
Public Sub AP_SyncAll_WithTarget(Optional ByVal Silent As Boolean = True, _
                                 Optional ByVal changedBottomRow As Long = 0, _
                                 Optional ByVal changedTopRow As Long = 0, _
                                 Optional ByVal changedFirstCol As Long = 0, _
                                 Optional ByVal changedLastCol As Long = 0, _
                                 Optional ByVal protectChangedRows As Boolean = True, _
                                 Optional ByVal runRecordSync As Boolean = True)

    Dim prevEvents As Boolean, prevScreen As Boolean
    Dim prevCalc As XlCalculation

    prevEvents = Application.EnableEvents
    prevScreen = Application.ScreenUpdating
    prevCalc = Application.Calculation

    On Error GoTo EH

    Application.EnableEvents = False
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    Dim handledRecordSync As Boolean

    SyncRecordLinesCore Silent, changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows, False

    If runRecordSync Then
        handledRecordSync = TrySyncRecordsTableTargeted(Silent, changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows)

        If Not handledRecordSync Then
            AP_SyncRecordsTable Silent, True, False
        End If
    End If

    If prevCalc = xlCalculationAutomatic Then
        CalculateTouchedLineTableSlice changedTopRow, changedBottomRow, (Not mDeferredLineFormulasPending And Not mDeferredLineCfPending)
    End If

CleanExit:
    Application.Calculation = prevCalc
    Application.ScreenUpdating = prevScreen
    Application.EnableEvents = prevEvents
    Exit Sub

EH:
    If Not Silent Then
        MsgBox "AP_SyncAll_WithTarget failed: " & Err.Description, vbExclamation
    End If
    Resume CleanExit
End Sub

Private Function TrySyncRecordsTableTargeted(ByVal Silent As Boolean, _
                                              ByVal changedBottomRow As Long, _
                                              ByVal changedTopRow As Long, _
                                              ByVal changedFirstCol As Long, _
                                              ByVal changedLastCol As Long, _
                                              ByVal protectChangedRows As Boolean) As Boolean

    On Error GoTo FallbackFullSync

    Dim wb As Workbook
    Set wb = ThisWorkbook

    Dim wsInv As Worksheet
    Dim wsLines As Worksheet
    Set wsInv = wb.Worksheets(SH_RECORDS)
    Set wsLines = wb.Worksheets(SH_LINES)

    Dim loInv As ListObject
    Dim loLines As ListObject
    Set loInv = wsInv.ListObjects(TBL_RECORDS)
    Set loLines = wsLines.ListObjects(TBL_LINES)

    EnsureInternalColumn loLines, COL_LINE_KEY
    EnsureInternalColumn loInv, COL_RECORD_KEY

    Dim usedLineRows As Long
    usedLineRows = LastUsedLineNumberRowCount(loLines)

    Dim recordKeys As Collection
    Set recordKeys = RecordKeysFromLines(loLines, usedLineRows)

    Dim lcRecordKey As ListColumn
    Set lcRecordKey = GetListColumn(loInv, COL_RECORD_KEY)

    Dim userInputColumns As Collection
    Set userInputColumns = GetUserInputColumns(loInv, True)

    Dim desiredRows As Long
    desiredRows = recordKeys.Count
    If desiredRows < 1 Then desiredRows = 1

    Dim oldRows As Long
    oldRows = loInv.ListRows.Count

    Dim appendedStartRow As Long
    Dim appendedEndRow As Long

    SeedRecordKeysByPosition loInv, lcRecordKey, recordKeys

    Dim affectedStartRow As Long
    Dim affectedEndRow As Long
    ResolveAffectedRecordRowBounds loLines, usedLineRows, changedTopRow, changedBottomRow, protectChangedRows, affectedStartRow, affectedEndRow

    If Not protectChangedRows Then
        affectedEndRow = desiredRows
    End If

    ' Record-number sequencing depends on prior record rows, so any affected
    ' record row can change the numbering for the rest of the table.
    If affectedStartRow > 0 Then
        affectedEndRow = desiredRows
    End If

    If RecordKeysMatchTable(lcRecordKey, recordKeys) Then
        RecalculateRecordTableSlice loInv, affectedStartRow, affectedEndRow
        TrySyncRecordsTableTargeted = True
        Exit Function
    End If

    If desiredRows > oldRows Then
        If RecordKeysMatchPrefix(lcRecordKey, recordKeys, oldRows) Then
            ResizeListObjectDataRows loInv, desiredRows
            ApplyListObjectRowFormatsFromPreviousRow loInv, oldRows + 1, desiredRows
            appendedStartRow = oldRows + 1
            appendedEndRow = desiredRows
            Set lcRecordKey = GetListColumn(loInv, COL_RECORD_KEY)

            ApplyRecordKeyAppend loInv, lcRecordKey, userInputColumns, recordKeys, oldRows + 1, desiredRows

            If affectedStartRow <= 0 Then affectedStartRow = oldRows
            If affectedStartRow < 1 Then affectedStartRow = 1
            If affectedEndRow < desiredRows Then affectedEndRow = desiredRows

            RecalculateRecordTableSlice loInv, affectedStartRow, affectedEndRow
            ApplyRecordNumberBordersFromPreviousRow loInv, appendedStartRow, appendedEndRow
            TrySyncRecordsTableTargeted = True
            Exit Function
        End If
    End If

FallbackFullSync:
    TrySyncRecordsTableTargeted = False
End Function

Public Sub AP_QueueSyncAll_WithTarget(Optional ByVal Silent As Boolean = True, _
                                      Optional ByVal changedBottomRow As Long = 0, _
                                      Optional ByVal changedTopRow As Long = 0, _
                                      Optional ByVal changedFirstCol As Long = 0, _
                                      Optional ByVal changedLastCol As Long = 0, _
                                      Optional ByVal protectChangedRows As Boolean = True)

    On Error GoTo EH

    Dim boundaryAffecting As Boolean
    Dim recordAffecting As Boolean
    boundaryAffecting = DetectBoundaryAffectingChange(changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows)
    recordAffecting = ChangeMayAffectRecords(changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows)

    Dim currentLineRows As Long
    currentLineRows = CurrentLinesTableRowCount()

    If mLastKnownLinesTableRows = 0 Then
        mLastKnownLinesTableRows = currentLineRows
    End If

    If (mEditPerfModeEnabled Or IsLinesSheetActive()) Then
        MarkDeferredLineWork
    ElseIf currentLineRows > mLastKnownLinesTableRows Then
        MarkDeferredLineWork
    ElseIf IsLikelyLinesGrowthChange(changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows) Then
        MarkDeferredLineWork
    End If

    If ManagedLineFormulaBackfillNeeded(changedTopRow, changedBottomRow) Then
        mDeferredLineFormulasPending = True
        TryApplyImmediateLineFormulaFeedback changedTopRow, changedBottomRow
    End If

    If currentLineRows > 0 Then
        mLastKnownLinesTableRows = currentLineRows
    End If

    If Not mSyncPending Then
        mPendingBottomRow = changedBottomRow
        mPendingTopRow = changedTopRow
        mPendingFirstCol = changedFirstCol
        mPendingLastCol = changedLastCol
        mPendingProtectRows = protectChangedRows
        mPendingRunRecordSync = recordAffecting
        mPendingSilent = Silent
    Else
        MergePendingSyncBounds changedBottomRow, changedTopRow, changedFirstCol, changedLastCol
        mPendingProtectRows = (mPendingProtectRows Or protectChangedRows)

        If Not mPendingRunRecordSync Then
            mPendingRunRecordSync = recordAffecting
        End If

        mPendingSilent = (mPendingSilent And Silent)
    End If

    mSyncPending = True
    Application.StatusBar = STATUS_SYNC_PENDING

    If recordAffecting Then
        CancelQueuedSyncRun
        AP_RunQueuedSync
    Else
        ScheduleQueuedSyncRun
    End If
    Exit Sub

EH:
    AP_ResetPerfModeSafety
    AP_SyncAll_WithTarget Silent, changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows, recordAffecting
End Sub

Public Sub AP_RunQueuedSync()
    Dim runSilent As Boolean
    runSilent = True
    Dim shouldFlushDeferredAfterRun As Boolean

    On Error GoTo EH

    If mSyncInFlight Then Exit Sub
    shouldFlushDeferredAfterRun = mFlushDeferredAfterExitPending

    If Not mSyncPending Then
        mSyncRunScheduled = False

        If shouldFlushDeferredAfterRun Then
            If mDeferredLineFormulasPending Or mDeferredLineCfPending Or mDeferredRecordSyncPending Then
                mSyncInFlight = True
                Application.StatusBar = STATUS_SYNC_RUNNING
                AP_FlushDeferredLineWork runSilent
                mFlushDeferredAfterExitPending = False
                GoTo CleanExit
            End If

            mFlushDeferredAfterExitPending = False
        End If

        If mDeferredLineFormulasPending Or mDeferredLineCfPending Or mDeferredRecordSyncPending Then
            Application.StatusBar = STATUS_SYNC_FAST_EDIT & " (deferred refresh)"
        Else
            Application.StatusBar = False
        End If
        Exit Sub
    End If

    Dim changedBottomRow As Long
    Dim changedTopRow As Long
    Dim changedFirstCol As Long
    Dim changedLastCol As Long
    Dim protectChangedRows As Boolean
    Dim runRecordSync As Boolean

    changedBottomRow = mPendingBottomRow
    changedTopRow = mPendingTopRow
    changedFirstCol = mPendingFirstCol
    changedLastCol = mPendingLastCol
    protectChangedRows = mPendingProtectRows
    runRecordSync = mPendingRunRecordSync
    runSilent = mPendingSilent

    ResetQueuedSyncState
    mSyncInFlight = True
    Application.StatusBar = STATUS_SYNC_RUNNING

    AP_SyncAll_WithTarget runSilent, changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows, runRecordSync

    If shouldFlushDeferredAfterRun Then
        AP_FlushDeferredLineWork runSilent
        mFlushDeferredAfterExitPending = False
    End If

CleanExit:
    mSyncInFlight = False
    mLastKnownLinesTableRows = CurrentLinesTableRowCount()

    If mSyncPending Then
        Application.StatusBar = STATUS_SYNC_PENDING
        ScheduleQueuedSyncRun
    ElseIf mDeferredLineFormulasPending Or mDeferredLineCfPending Or mDeferredRecordSyncPending Then
        Application.StatusBar = STATUS_SYNC_FAST_EDIT & " (deferred refresh)"
    Else
        Application.StatusBar = False
    End If
    Exit Sub

EH:
    mSyncInFlight = False
    AP_ResetPerfModeSafety

    If Not runSilent Then
        MsgBox "AP_RunQueuedSync failed: " & Err.Description, vbExclamation
    End If

    If mSyncPending Then
        Application.StatusBar = STATUS_SYNC_PENDING
        ScheduleQueuedSyncRun
    Else
        Application.StatusBar = False
    End If
End Sub

Public Sub AP_FlushQueuedSync(Optional ByVal Silent As Boolean = True, Optional ByVal forceDeferredWork As Boolean = True)
    If Not mSyncPending Then
        If forceDeferredWork Then AP_FlushDeferredLineWork Silent
        Exit Sub
    End If

    If Not Silent Then
        mPendingSilent = False
    End If

    CancelQueuedSyncRun
    AP_RunQueuedSync

    If forceDeferredWork Then AP_FlushDeferredLineWork Silent
End Sub

Public Sub AP_HandleLinesSheetDeactivate(Optional ByVal Silent As Boolean = True)
    On Error GoTo EH

    AP_SetPerformanceEditMode False

    If Not mSyncPending And _
       Not mDeferredLineFormulasPending And _
       Not mDeferredLineCfPending And _
       Not mDeferredRecordSyncPending Then
        mFlushDeferredAfterExitPending = False
        Application.StatusBar = False
        Exit Sub
    End If

    If Not Silent And mSyncPending Then
        mPendingSilent = False
    End If

    mFlushDeferredAfterExitPending = True

    If mSyncPending Then
        Application.StatusBar = STATUS_SYNC_PENDING
    Else
        Application.StatusBar = STATUS_SYNC_RUNNING
    End If

    ScheduleQueuedSyncRun
    Exit Sub

EH:
    AP_ResetPerfModeSafety
End Sub

Private Sub CancelQueuedSyncRun()
    Dim procName As String
    procName = "'" & ThisWorkbook.Name & "'!AP_RunQueuedSync"

    If mSyncRunScheduled Then
        On Error Resume Next
        Application.OnTime EarliestTime:=mScheduledRunAt, Procedure:=procName, Schedule:=False
        On Error GoTo 0
    End If

    mSyncRunScheduled = False
End Sub

Private Sub ScheduleQueuedSyncRun()
    Dim procName As String
    procName = "'" & ThisWorkbook.Name & "'!AP_RunQueuedSync"

    If mSyncRunScheduled Then
        On Error Resume Next
        Application.OnTime EarliestTime:=mScheduledRunAt, Procedure:=procName, Schedule:=False
        On Error GoTo 0
    End If

    mScheduledRunAt = DateAdd("s", DebounceDelaySeconds(), Now)
    mSyncRunScheduled = True

    On Error Resume Next
    Application.OnTime EarliestTime:=mScheduledRunAt, Procedure:=procName, Schedule:=True

    If Err.Number <> 0 Then
        Err.Clear
        mScheduledRunAt = Now + (1# / 86400#)
        Application.OnTime EarliestTime:=mScheduledRunAt, Procedure:=procName, Schedule:=True
    End If
    On Error GoTo 0
End Sub

Private Function DebounceDelaySeconds() As Long
    ' Application.OnTime uses Date precision and effectively schedules at second granularity.
    DebounceDelaySeconds = CLng((SYNC_DEBOUNCE_MS + 999) \ 1000)
    If DebounceDelaySeconds < 1 Then DebounceDelaySeconds = 1
End Function

Private Sub ResetQueuedSyncState()
    mSyncPending = False
    mSyncRunScheduled = False
    mPendingBottomRow = 0
    mPendingTopRow = 0
    mPendingFirstCol = 0
    mPendingLastCol = 0
    mPendingProtectRows = False
    mPendingRunRecordSync = False
    mPendingSilent = True
End Sub

Private Sub MergePendingSyncBounds(ByVal changedBottomRow As Long, _
                                   ByVal changedTopRow As Long, _
                                   ByVal changedFirstCol As Long, _
                                   ByVal changedLastCol As Long)

    mPendingTopRow = MergeMinPositiveLong(mPendingTopRow, changedTopRow)
    mPendingBottomRow = MaxLong(mPendingBottomRow, changedBottomRow)
    mPendingFirstCol = MergeMinPositiveLong(mPendingFirstCol, changedFirstCol)
    mPendingLastCol = MaxLong(mPendingLastCol, changedLastCol)
End Sub

Private Function MergeMinPositiveLong(ByVal existingValue As Long, ByVal incomingValue As Long) As Long
    If existingValue <= 0 Then
        MergeMinPositiveLong = incomingValue
    ElseIf incomingValue <= 0 Then
        MergeMinPositiveLong = existingValue
    Else
        MergeMinPositiveLong = MinLong(existingValue, incomingValue)
    End If
End Function

Private Sub MarkDeferredLineWork()
    mDeferredLineCfPending = True
    AP_SetPerformanceEditMode True
End Sub

Public Sub AP_SetPerformanceEditMode(ByVal enabled As Boolean)
    On Error GoTo SafeExit

    Dim wsLines As Worksheet
    Dim wsInv As Worksheet

    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)
    Set wsInv = ThisWorkbook.Worksheets(SH_RECORDS)

    If enabled Then
        If Not mHaveSavedAutoFill Then
            On Error Resume Next
            mSavedAutoFillFormulasInLists = Application.AutoCorrect.AutoFillFormulasInLists
            mHaveSavedAutoFill = (Err.Number = 0)
            Err.Clear
            On Error GoTo SafeExit
        End If

        If Not mHaveSavedAutoExpand Then
            On Error Resume Next
            mSavedAutoExpandListRange = Application.AutoCorrect.AutoExpandListRange
            mHaveSavedAutoExpand = (Err.Number = 0)
            Err.Clear
            On Error GoTo SafeExit
        End If

        If Not mHaveSavedLineCf Then
            On Error Resume Next
            mSavedLineCfCalcEnabled = wsLines.EnableFormatConditionsCalculation
            mHaveSavedLineCf = (Err.Number = 0)
            Err.Clear
            On Error GoTo SafeExit
        End If

        If Not mHaveSavedLinesEnableCalculation Then
            On Error Resume Next
            mSavedLinesEnableCalculation = wsLines.EnableCalculation
            mHaveSavedLinesEnableCalculation = (Err.Number = 0)
            Err.Clear
            On Error GoTo SafeExit
        End If

        If Not mHaveSavedRecordsEnableCalculation Then
            On Error Resume Next
            mSavedRecordsEnableCalculation = wsInv.EnableCalculation
            mHaveSavedRecordsEnableCalculation = (Err.Number = 0)
            Err.Clear
            On Error GoTo SafeExit
        End If

        DisableManagedSheetsCalculationForFastEdit
        mEditPerfModeEnabled = True
        mLastKnownLinesTableRows = CurrentLinesTableRowCount()

        If Not mSyncPending Then
            Application.StatusBar = STATUS_SYNC_FAST_EDIT
        End If
    Else
        If mHaveSavedAutoFill Then
            On Error Resume Next
            Application.AutoCorrect.AutoFillFormulasInLists = CBool(mSavedAutoFillFormulasInLists)
            Err.Clear
            On Error GoTo SafeExit
        End If

        If mHaveSavedAutoExpand Then
            On Error Resume Next
            Application.AutoCorrect.AutoExpandListRange = CBool(mSavedAutoExpandListRange)
            Err.Clear
            On Error GoTo SafeExit
        End If

        If mHaveSavedLineCf Then
            On Error Resume Next
            wsLines.EnableFormatConditionsCalculation = CBool(mSavedLineCfCalcEnabled)
            Err.Clear
            On Error GoTo SafeExit
        End If

        If mHaveSavedLinesEnableCalculation Then
            On Error Resume Next
            wsLines.EnableCalculation = CBool(mSavedLinesEnableCalculation)
            Err.Clear
            On Error GoTo SafeExit
        End If

        If mHaveSavedRecordsEnableCalculation Then
            On Error Resume Next
            wsInv.EnableCalculation = CBool(mSavedRecordsEnableCalculation)
            Err.Clear
            On Error GoTo SafeExit
        End If

        mEditPerfModeEnabled = False

        If Not mSyncPending Then
            Application.StatusBar = False
        End If
    End If

SafeExit:
End Sub

Public Sub AP_FlushDeferredLineWork(Optional ByVal Silent As Boolean = True)
    FlushDeferredLineWorkCore Silent, 0, 0, False
End Sub

Private Sub FlushDeferredLineWorkCore(ByVal Silent As Boolean, _
                                      Optional ByVal changedTopRow As Long = 0, _
                                      Optional ByVal changedBottomRow As Long = 0, _
                                      Optional ByVal useTargetSlice As Boolean = False)
    If Not mDeferredLineFormulasPending And Not mDeferredLineCfPending And Not mDeferredRecordSyncPending Then Exit Sub

    Dim prevEvents As Boolean, prevScreen As Boolean
    Dim prevCalc As XlCalculation
    Dim t0 As Double

    prevEvents = Application.EnableEvents
    prevScreen = Application.ScreenUpdating
    prevCalc = Application.Calculation
    t0 = Timer

    On Error GoTo EH

    Application.EnableEvents = False
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    EnsureManagedSheetsCalculationEnabled

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    If mDeferredLineFormulasPending Then
        ApplyDeferredLineFormulas loLines, changedTopRow, changedBottomRow, useTargetSlice
        CalculateLineFormulaSlice loLines, changedTopRow, changedBottomRow, useTargetSlice
    End If

    If mDeferredLineCfPending Then
        On Error Resume Next
        wsLines.EnableFormatConditionsCalculation = True
        On Error GoTo EH
    End If

    If mDeferredRecordSyncPending Then
        AP_SyncRecordsTable Silent, True, False
    End If

    mDeferredLineFormulasPending = False
    mDeferredLineCfPending = False
    mDeferredRecordSyncPending = False

    If IsLinesSheetActive() Then
        AP_SetPerformanceEditMode True
    Else
        AP_SetPerformanceEditMode False
    End If

    TracePerf "flush deferred line work secs=" & Format$(ElapsedTimerSeconds(t0), "0.000")

CleanExit:
    Application.Calculation = prevCalc
    Application.ScreenUpdating = prevScreen
    Application.EnableEvents = prevEvents
    Exit Sub

EH:
    AP_ResetPerfModeSafety
    If Not Silent Then
        MsgBox "AP_FlushDeferredLineWork failed: " & Err.Description, vbExclamation
    End If
    Resume CleanExit
End Sub

Public Sub AP_BeforeExportFlush(Optional ByVal Silent As Boolean = True)
    AP_FlushQueuedSync Silent, True
End Sub

Public Sub AP_ResetPerfModeSafety()
    On Error Resume Next
    mDeferredLineFormulasPending = False
    mDeferredLineCfPending = False
    mDeferredRecordSyncPending = False
    mFlushDeferredAfterExitPending = False
    mLastKnownLinesTableRows = 0
    AP_SetPerformanceEditMode False
    On Error GoTo 0
End Sub

Private Sub ApplyDeferredLineFormulas(ByVal loLines As ListObject, _
                                      Optional ByVal changedTopRow As Long = 0, _
                                      Optional ByVal changedBottomRow As Long = 0, _
                                      Optional ByVal useTargetSlice As Boolean = False)
    If loLines Is Nothing Then Exit Sub
    If loLines.DataBodyRange Is Nothing Then Exit Sub

    Dim usedRows As Long
    usedRows = LastUsedLineNumberRowCount(loLines)
    If usedRows < 1 Then usedRows = 1

    Dim startIx As Long
    Dim endIx As Long
    ResolveLineSliceBounds loLines, usedRows, changedTopRow, changedBottomRow, useTargetSlice, startIx, endIx
    If endIx < startIx Then Exit Sub

    Dim lc As ListColumn
    For Each lc In loLines.ListColumns
        If IsManagedFormulaColumn(loLines.Name, CStr(lc.Name)) Then
            ApplyColumnFormulaToSlice lc, usedRows, startIx, endIx
        End If
    Next lc
End Sub

Private Sub TryApplyImmediateLineFormulaFeedback(ByVal changedTopRow As Long, _
                                                 ByVal changedBottomRow As Long)
    If changedTopRow <= 0 Or changedBottomRow < changedTopRow Then Exit Sub
    If Not (mEditPerfModeEnabled Or IsLinesSheetActive()) Then Exit Sub

    On Error GoTo SafeExit

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    On Error Resume Next
    If Not wsLines.EnableCalculation Then wsLines.EnableCalculation = True
    On Error GoTo SafeExit

    ApplyDeferredLineFormulas loLines, changedTopRow, changedBottomRow, True
    CalculateLineFormulaSlice loLines, changedTopRow, changedBottomRow, True
    mDeferredLineFormulasPending = False

SafeExit:
End Sub

Private Function ManagedLineFormulaBackfillNeeded(ByVal changedTopRow As Long, _
                                                  ByVal changedBottomRow As Long) As Boolean
    On Error GoTo SafeExit

    If changedTopRow <= 0 Or changedBottomRow < changedTopRow Then Exit Function

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    If loLines Is Nothing Then Exit Function
    If loLines.DataBodyRange Is Nothing Then Exit Function

    Dim usedRows As Long
    usedRows = LastUsedLineNumberRowCount(loLines)
    If usedRows < 1 Then usedRows = 1

    Dim startIx As Long
    Dim endIx As Long
    ResolveLineSliceBounds loLines, usedRows, changedTopRow, changedBottomRow, True, startIx, endIx
    If endIx < startIx Then Exit Function

    Dim lc As ListColumn
    For Each lc In loLines.ListColumns
        If IsManagedFormulaColumn(loLines.Name, CStr(lc.Name)) Then
            If LineFormulaSliceNeedsBackfill(lc, startIx, endIx) Then
                ManagedLineFormulaBackfillNeeded = True
                Exit Function
            End If
        End If
    Next lc

SafeExit:
End Function

Private Function LineFormulaSliceNeedsBackfill(ByVal lc As ListColumn, _
                                               ByVal startIx As Long, _
                                               ByVal endIx As Long) As Boolean
    If lc Is Nothing Then Exit Function
    If lc.DataBodyRange Is Nothing Then Exit Function

    Dim rowCount As Long
    rowCount = lc.DataBodyRange.Rows.Count
    If rowCount < 1 Then Exit Function

    If startIx < 1 Then startIx = 1
    If endIx > rowCount Then endIx = rowCount
    If endIx < startIx Then Exit Function

    Dim hasFormulaState As Variant
    hasFormulaState = lc.DataBodyRange.Cells(startIx, 1).Resize(endIx - startIx + 1, 1).HasFormula

    If IsNull(hasFormulaState) Then
        LineFormulaSliceNeedsBackfill = True
    Else
        LineFormulaSliceNeedsBackfill = (CBool(hasFormulaState) = False)
    End If
End Function

Private Sub ApplyColumnFormulaToSlice(ByVal lc As ListColumn, _
                                      ByVal usedRows As Long, _
                                      ByVal startIx As Long, _
                                      ByVal endIx As Long)
    If lc Is Nothing Then Exit Sub
    If lc.DataBodyRange Is Nothing Then Exit Sub

    Dim rowCount As Long
    rowCount = lc.DataBodyRange.Rows.Count
    If rowCount < 1 Then Exit Sub

    If usedRows > rowCount Then usedRows = rowCount
    If usedRows < 1 Then Exit Sub
    If startIx < 1 Then startIx = 1
    If endIx > usedRows Then endIx = usedRows
    If endIx < startIx Then Exit Sub

    Dim formulaText As String
    On Error Resume Next
    formulaText = CStr(lc.DataBodyRange.Cells(1, 1).Formula2)
    On Error GoTo 0

    If Len(formulaText) = 0 Then
        formulaText = CStr(lc.DataBodyRange.Cells(1, 1).Formula)
    End If
    If Len(formulaText) = 0 Then Exit Sub

    Dim rngTarget As Range
    Set rngTarget = lc.DataBodyRange.Cells(startIx, 1).Resize(endIx - startIx + 1, 1)

    On Error Resume Next
    rngTarget.Formula2 = formulaText
    If Err.Number <> 0 Then
        Err.Clear
        rngTarget.Formula = formulaText
    End If
    On Error GoTo 0
End Sub

Private Sub CalculateListColumnSlice(ByVal lc As ListColumn, ByVal startIx As Long, ByVal endIx As Long)
    If lc Is Nothing Then Exit Sub
    If lc.DataBodyRange Is Nothing Then Exit Sub

    Dim rowCount As Long
    rowCount = lc.DataBodyRange.Rows.Count
    If rowCount < 1 Then Exit Sub

    If startIx < 1 Then startIx = 1
    If endIx > rowCount Then endIx = rowCount
    If endIx < startIx Then Exit Sub

    lc.DataBodyRange.Cells(startIx, 1).Resize(endIx - startIx + 1, 1).Calculate
End Sub

Private Function IsLikelyLinesGrowthChange(ByVal changedBottomRow As Long, _
                                          ByVal changedTopRow As Long, _
                                          ByVal changedFirstCol As Long, _
                                          ByVal changedLastCol As Long, _
                                          ByVal protectChangedRows As Boolean) As Boolean

    On Error GoTo ConservativeFalse

    If changedBottomRow <= 0 Or changedTopRow <= 0 Then Exit Function

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    Dim firstDataRow As Long
    firstDataRow = loLines.HeaderRowRange.Row + 1

    Dim tableBottomRow As Long
    tableBottomRow = firstDataRow + loLines.ListRows.Count - 1

    If protectChangedRows And changedTopRow > tableBottomRow Then
        If RangeHasAnyContent(wsLines, changedTopRow, changedBottomRow, changedFirstCol, changedLastCol) Then
            IsLikelyLinesGrowthChange = True
            Exit Function
        End If
    End If

    If changedBottomRow > tableBottomRow Then
        IsLikelyLinesGrowthChange = True
        Exit Function
    End If

    If changedTopRow >= firstDataRow And changedBottomRow > changedTopRow Then
        IsLikelyLinesGrowthChange = True
        Exit Function
    End If

ConservativeFalse:
End Function

Private Function DetectBoundaryAffectingChange(ByVal changedBottomRow As Long, _
                                                ByVal changedTopRow As Long, _
                                                ByVal changedFirstCol As Long, _
                                                ByVal changedLastCol As Long, _
                                                ByVal protectChangedRows As Boolean) As Boolean

    On Error GoTo ConservativeTrue

    If changedBottomRow <= 0 Or changedTopRow <= 0 Then
        DetectBoundaryAffectingChange = True
        Exit Function
    End If

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    Dim firstDataRow As Long
    firstDataRow = loLines.HeaderRowRange.Row + 1

    Dim tableBottomRow As Long
    tableBottomRow = firstDataRow + loLines.ListRows.Count - 1

    If changedBottomRow > tableBottomRow Then
        DetectBoundaryAffectingChange = True
        Exit Function
    End If

    If changedTopRow <= tableBottomRow And changedBottomRow >= firstDataRow Then
        DetectBoundaryAffectingChange = True
        Exit Function
    End If

    Dim lcLineNumber As ListColumn
    Set lcLineNumber = GetListColumn(loLines, COL_LINE_NUMBER, "*Line Number")

    If lcLineNumber Is Nothing Then
        DetectBoundaryAffectingChange = True
        Exit Function
    End If

    Dim lineNumberAbsCol As Long
    lineNumberAbsCol = lcLineNumber.Range.Column

    If changedFirstCol <= lineNumberAbsCol And changedLastCol >= lineNumberAbsCol Then
        DetectBoundaryAffectingChange = True
        Exit Function
    End If

    If changedTopRow <= tableBottomRow And changedBottomRow >= firstDataRow Then
        Dim startIx As Long
        Dim endIx As Long

        startIx = MaxLong(1, changedTopRow - firstDataRow + 1)
        endIx = MinLong(loLines.ListRows.Count, changedBottomRow - firstDataRow + 1)

        If endIx >= startIx Then
            Dim rngLineSlice As Range
            Set rngLineSlice = lcLineNumber.DataBodyRange.Cells(startIx, 1).Resize(endIx - startIx + 1, 1)

            If Application.CountBlank(rngLineSlice) > 0 Then
                DetectBoundaryAffectingChange = True
                Exit Function
            End If
        End If
    End If

    If protectChangedRows And changedTopRow > tableBottomRow Then
        If RangeHasAnyContent(wsLines, changedTopRow, changedBottomRow, changedFirstCol, changedLastCol) Then
            DetectBoundaryAffectingChange = True
            Exit Function
        End If
    End If

    DetectBoundaryAffectingChange = False
    Exit Function

ConservativeTrue:
    DetectBoundaryAffectingChange = True
End Function

Private Sub ResolveAffectedRecordRowBounds(ByVal loLines As ListObject, _
                                            ByVal usedRows As Long, _
                                            ByVal changedTopRow As Long, _
                                            ByVal changedBottomRow As Long, _
                                            ByVal protectChangedRows As Boolean, _
                                            ByRef startIx As Long, _
                                            ByRef endIx As Long)

    startIx = 1
    endIx = 1

    If loLines Is Nothing Then Exit Sub
    If loLines.DataBodyRange Is Nothing Then Exit Sub
    If usedRows < 1 Then Exit Sub

    Dim firstDataRow As Long
    firstDataRow = loLines.DataBodyRange.Row

    Dim localStart As Long
    Dim localEnd As Long

    localStart = changedTopRow - firstDataRow + 1
    localEnd = changedBottomRow - firstDataRow + 1

    If localStart < 1 Then localStart = 1
    If localEnd < localStart Then localEnd = localStart
    If localEnd > usedRows Then localEnd = usedRows

    Dim lcLineNumber As ListColumn
    Set lcLineNumber = GetListColumn(loLines, COL_LINE_NUMBER, "*Line Number")
    If lcLineNumber Is Nothing Then Exit Sub

    Dim lineNumberValues As Variant
    lineNumberValues = ColumnRangeValue2D(lcLineNumber.DataBodyRange.Resize(usedRows, 1), usedRows)

    Dim recordIx As Long
    Dim currentRecordStart As Long
    currentRecordStart = 1

    Dim rowIndex As Long
    For rowIndex = 1 To usedRows
        If IsLineStartValue(lineNumberValues(rowIndex, 1)) Then
            recordIx = recordIx + 1

            If rowIndex <= localStart Then
                currentRecordStart = recordIx
            End If
        End If

        If rowIndex = localStart Then
            startIx = MaxLong(1, currentRecordStart)
        End If

        If rowIndex >= localEnd Then
            endIx = MaxLong(startIx, recordIx)
            Exit Sub
        End If
    Next rowIndex

    If protectChangedRows And changedBottomRow > (firstDataRow + usedRows - 1) Then
        endIx = MaxLong(endIx, recordIx + 1)
    Else
        endIx = MaxLong(startIx, recordIx)
    End If
End Sub

Private Sub ApplyRecordTableFormulas(ByVal loInv As ListObject)
    If loInv Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub

    Dim usedRows As Long
    usedRows = loInv.ListRows.Count
    If usedRows < 1 Then usedRows = 1

    Dim lc As ListColumn
    For Each lc In loInv.ListColumns
        If IsManagedFormulaColumn(loInv.Name, CStr(lc.Name)) Then
            ApplyColumnFormulaToSlice lc, usedRows, 1, usedRows
        End If
    Next lc
End Sub

Private Sub ApplyRecordTableFormulasSlice(ByVal loInv As ListObject, ByVal startIx As Long, ByVal endIx As Long)
    If loInv Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub

    Dim rowCount As Long
    rowCount = loInv.ListRows.Count
    If rowCount < 1 Then Exit Sub

    If startIx < 1 Then startIx = 1
    If endIx > rowCount Then endIx = rowCount
    If endIx < startIx Then Exit Sub

    Dim lc As ListColumn
    For Each lc In loInv.ListColumns
        If IsManagedFormulaColumn(loInv.Name, CStr(lc.Name)) Then
            ApplyColumnFormulaToSlice lc, rowCount, startIx, endIx
        End If
    Next lc
End Sub

Private Sub RecalculateRecordTable(ByVal loInv As ListObject)
    If loInv Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub

    ApplyRecordTableFormulas loInv
    CalculateManagedRecordColumns loInv, COL_INV_NUMBER_FORMULA
    CalculateRecordManagedColumn loInv, COL_INV_NUMBER_FORMULA
    loInv.DataBodyRange.Calculate
End Sub

Private Sub RecalculateRecordTableSlice(ByVal loInv As ListObject, ByVal startIx As Long, ByVal endIx As Long)
    If loInv Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub

    Dim rowCount As Long
    rowCount = loInv.ListRows.Count
    If rowCount < 1 Then Exit Sub

    If startIx < 1 Then startIx = 1
    If endIx > rowCount Then endIx = rowCount
    If endIx < startIx Then Exit Sub

    ApplyRecordTableFormulasSlice loInv, startIx, endIx
    CalculateManagedRecordColumnsSlice loInv, startIx, endIx, COL_INV_NUMBER_FORMULA
    CalculateRecordManagedColumnSlice loInv, COL_INV_NUMBER_FORMULA, startIx, endIx
    loInv.DataBodyRange.Rows(startIx & ":" & endIx).Calculate
End Sub

Private Sub CalculateManagedRecordColumnsSlice(ByVal loInv As ListObject, _
                                                ByVal startIx As Long, _
                                                ByVal endIx As Long, _
                                                Optional ByVal skipHeaderName As String = "")
    If loInv Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub

    Dim normalizedSkipHeader As String
    normalizedSkipHeader = LCase$(Trim$(skipHeaderName))

    Dim lc As ListColumn
    For Each lc In loInv.ListColumns
        If IsManagedFormulaColumn(loInv.Name, CStr(lc.Name)) Then
            If normalizedSkipHeader = "" Or LCase$(Trim$(CStr(lc.Name))) <> normalizedSkipHeader Then
                CalculateListColumnSlice lc, startIx, endIx
            End If
        End If
    Next lc
End Sub

Private Sub CalculateRecordManagedColumnSlice(ByVal loInv As ListObject, _
                                               ByVal headerName As String, _
                                               ByVal startIx As Long, _
                                               ByVal endIx As Long)
    If loInv Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub

    Dim lc As ListColumn
    Set lc = GetListColumn(loInv, headerName)
    If lc Is Nothing Then Exit Sub

    CalculateListColumnSlice lc, startIx, endIx
End Sub

Private Sub CalculateManagedRecordColumns(ByVal loInv As ListObject, Optional ByVal skipHeaderName As String = "")
    If loInv Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub

    Dim normalizedSkipHeader As String
    normalizedSkipHeader = LCase$(Trim$(skipHeaderName))

    Dim lc As ListColumn
    For Each lc In loInv.ListColumns
        If IsManagedFormulaColumn(loInv.Name, CStr(lc.Name)) Then
            If normalizedSkipHeader = "" Or LCase$(Trim$(CStr(lc.Name))) <> normalizedSkipHeader Then
                If Not lc.DataBodyRange Is Nothing Then
                    lc.DataBodyRange.Calculate
                End If
            End If
        End If
    Next lc
End Sub

Private Sub CalculateRecordManagedColumn(ByVal loInv As ListObject, ByVal headerName As String)
    If loInv Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub

    Dim lc As ListColumn
    Set lc = GetListColumn(loInv, headerName)
    If lc Is Nothing Then Exit Sub
    If lc.DataBodyRange Is Nothing Then Exit Sub

    lc.DataBodyRange.Calculate
End Sub

Private Sub SyncRecordLinesCore(ByVal Silent As Boolean, _
                                 ByVal changedBottomRow As Long, _
                                 ByVal changedTopRow As Long, _
                                 ByVal changedFirstCol As Long, _
                                 ByVal changedLastCol As Long, _
                                 ByVal protectChangedRows As Boolean, _
                                 ByVal ManageAppState As Boolean)

    Dim prevEvents As Boolean, prevScreen As Boolean
    Dim prevCalc As XlCalculation

    prevEvents = Application.EnableEvents
    prevScreen = Application.ScreenUpdating
    prevCalc = Application.Calculation

    On Error GoTo EH

    If ManageAppState Then
        Application.EnableEvents = False
        Application.ScreenUpdating = False
        Application.Calculation = xlCalculationManual
    End If

    Dim wb As Workbook: Set wb = ThisWorkbook
    Dim wsLines As Worksheet: Set wsLines = wb.Worksheets(SH_LINES)
    Dim loLines As ListObject: Set loLines = wsLines.ListObjects(TBL_LINES)

    EnsureInternalColumn loLines, COL_LINE_KEY

    Dim firstDataRow As Long
    firstDataRow = loLines.HeaderRowRange.Row + 1

    Dim currentRows As Long
    currentRows = loLines.ListRows.Count

    Dim tableBottomRow As Long
    tableBottomRow = firstDataRow + currentRows - 1

    If changedTopRow > 0 Then
        BackfillLineNumberDefaults_ForChangedRows loLines, changedTopRow, MinLong(changedBottomRow, tableBottomRow)
    End If

    Dim requiredRows As Long
    requiredRows = LastUsedLineNumberRowCount(loLines)

    If protectChangedRows And changedBottomRow >= firstDataRow Then
        If RangeHasAnyContent(wsLines, changedTopRow, changedBottomRow, changedFirstCol, changedLastCol) Then
            requiredRows = MaxLong(requiredRows, changedBottomRow - firstDataRow + 1)
        End If
    End If

    If requiredRows < 1 Then requiredRows = 1

    If loLines.ListRows.Count < requiredRows Then
        ResizeListObjectDataRows loLines, GrowLinesTableRowTarget(requiredRows)
        mLastKnownLinesTableRows = loLines.ListRows.Count
    End If

    If changedTopRow > 0 Then
        BackfillLineNumberDefaults_ForChangedRows loLines, changedTopRow, changedBottomRow
    End If

    ApplyTableBottomBoundary loLines

CleanExit:
    If ManageAppState Then
        Application.Calculation = prevCalc
        Application.ScreenUpdating = prevScreen
        Application.EnableEvents = prevEvents
    End If
    Exit Sub

EH:
    If Not Silent Then
        MsgBox "AP_SyncRecordLinesTable failed: " & Err.Description, vbExclamation
    End If
    Resume CleanExit
End Sub

'Custom undo entry-point for DATA_RECORD_LINES Worksheet_Change.
'Replays Excel's last user action, then re-syncs dependent tables.
Public Sub AP_UndoRecordLinesChange()
    Dim prevEvents As Boolean
    prevEvents = Application.EnableEvents

    On Error GoTo CleanExit
    Application.EnableEvents = False

    CancelQueuedSyncRun
    ResetQueuedSyncState
    AP_ResetPerfModeSafety

    Application.Undo
    AP_SyncRecordLinesTable True
    AP_SyncRecordsTable True, True

CleanExit:
    Application.EnableEvents = prevEvents
End Sub

'One-time cleanup helper (run manually if you already have #VALUE! leftovers below the table)
Public Sub AP_CleanupRecordsOrphans(Optional ByVal Silent As Boolean = True)
    Dim prevEvents As Boolean, prevScreen As Boolean, prevCalc As XlCalculation
    prevEvents = Application.EnableEvents
    prevScreen = Application.ScreenUpdating
    prevCalc = Application.Calculation

    On Error GoTo EH
    Application.EnableEvents = False
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    Dim wsInv As Worksheet: Set wsInv = ThisWorkbook.Worksheets(SH_RECORDS)
    Dim loInv As ListObject: Set loInv = wsInv.ListObjects(TBL_RECORDS)

    Dim firstCol As Long, colCount As Long
    firstCol = loInv.Range.Column
    colCount = loInv.Range.Columns.Count

    Dim bottomRow As Long
    bottomRow = loInv.Range.Row + loInv.Range.Rows.Count - 1

    'Search below the table within its columns for ANY formulas/values (including leftover structured refs)
    Dim searchRng As Range
    Set searchRng = wsInv.Range(wsInv.Cells(bottomRow + 1, firstCol), _
                                wsInv.Cells(wsInv.Rows.Count, firstCol + colCount - 1))

    Dim lastCell As Range
    Set lastCell = searchRng.Find(What:="*", _
                                  After:=searchRng.Cells(1, 1), _
                                  LookIn:=xlFormulas, _
                                  LookAt:=xlPart, _
                                  SearchOrder:=xlByRows, _
                                  SearchDirection:=xlPrevious, _
                                  MatchCase:=False, _
                                  SearchFormat:=False)

    If Not lastCell Is Nothing Then
        ClearOrphanedTableArea wsInv, bottomRow + 1, lastCell.Row, firstCol, colCount
    End If

CleanExit:
    Application.Calculation = prevCalc
    Application.ScreenUpdating = prevScreen
    Application.EnableEvents = prevEvents
    Exit Sub

EH:
    If Not Silent Then
        MsgBox "AP_CleanupRecordsOrphans failed: " & Err.Description, vbExclamation
    End If
    Resume CleanExit
End Sub

'===== internal helpers =================================================

Private Sub BackfillLineNumberDefaults_ForChangedRows(ByVal loLines As ListObject, _
                                                      ByVal changedTopRow As Long, _
                                                      ByVal changedBottomRow As Long)

    If loLines.DataBodyRange Is Nothing Then Exit Sub

    Dim lcLineNumber As ListColumn
    Set lcLineNumber = GetListColumn(loLines, "Line Number", "*Line Number")
    If lcLineNumber Is Nothing Then Exit Sub

    Dim firstDataRow As Long
    firstDataRow = loLines.DataBodyRange.Row

    Dim startIx As Long, endIx As Long
    If changedTopRow <= 0 Or changedBottomRow <= 0 Then
        startIx = 1
        endIx = loLines.ListRows.Count
    Else
        startIx = changedTopRow - firstDataRow + 1
        endIx = changedBottomRow - firstDataRow + 1
        If startIx < 1 Then startIx = 1
        endIx = MinLong(endIx, loLines.ListRows.Count)
        If endIx < startIx Then Exit Sub
    End If

    Dim rowCount As Long
    rowCount = endIx - startIx + 1
    If rowCount < 1 Then Exit Sub

    Dim lastCol As Long
    lastCol = LastNonInternalColumnIndex(loLines)
    If lastCol < 1 Then Exit Sub

    Dim userInputIndexes As Collection
    Set userInputIndexes = GetUserInputColumnIndexes(loLines, lcLineNumber.Index)
    If userInputIndexes.Count = 0 Then Exit Sub

    Dim rowSlice As Range
    Set rowSlice = loLines.DataBodyRange.Cells(startIx, 1).Resize(rowCount, lastCol)

    Dim dataVals As Variant
    dataVals = rowSlice.Value2

    Dim lineVals As Variant
    lineVals = ColumnRangeValue2D(lcLineNumber.DataBodyRange.Cells(startIx, 1).Resize(rowCount, 1), rowCount)

    Dim rowIndex As Long
    Dim colItem As Variant
    Dim didChange As Boolean

    For rowIndex = 1 To rowCount
        If IsBlankLike(lineVals(rowIndex, 1)) Then
            For Each colItem In userInputIndexes
                If Not IsBlankLike(dataVals(rowIndex, CLng(colItem))) Then
                    lineVals(rowIndex, 1) = 1
                    didChange = True
                    Exit For
                End If
            Next colItem
        End If
    Next rowIndex

    If didChange Then
        lcLineNumber.DataBodyRange.Cells(startIx, 1).Resize(rowCount, 1).Value2 = lineVals
    End If
End Sub

Private Function RecordKeysFromLines(ByVal loLines As ListObject, Optional ByVal maxRows As Long = 0) As Collection
    Dim keys As New Collection
    Set RecordKeysFromLines = keys

    If loLines.DataBodyRange Is Nothing Then Exit Function

    Dim lcLineNumber As ListColumn
    Set lcLineNumber = GetListColumn(loLines, "Line Number", "*Line Number")
    If lcLineNumber Is Nothing Then Exit Function

    Dim lcLineKey As ListColumn
    Set lcLineKey = GetListColumn(loLines, COL_LINE_KEY)
    If lcLineKey Is Nothing Then Exit Function

    Dim seen As Object
    Set seen = CreateObject("Scripting.Dictionary")

    Dim limit As Long
    limit = loLines.ListRows.Count
    If maxRows > 0 Then limit = MinLong(limit, maxRows)
    If limit < 1 Then Exit Function

    Dim lineNumberValues As Variant
    lineNumberValues = ColumnRangeValue2D(lcLineNumber.DataBodyRange.Resize(limit, 1), limit)

    Dim lineKeyValues As Variant
    lineKeyValues = ColumnRangeValue2D(lcLineKey.DataBodyRange.Resize(limit, 1), limit)

    Dim didUpdateKeys As Boolean

    Dim rowIndex As Long
    For rowIndex = 1 To limit
        Dim lineNumberValue As Variant
        lineNumberValue = lineNumberValues(rowIndex, 1)

        If IsLineStartValue(lineNumberValue) Then
            Dim lineKey As String
            lineKey = Trim$(CStr(lineKeyValues(rowIndex, 1)))

            If Len(lineKey) = 0 Then
                lineKey = NewStableKey()
                lineKeyValues(rowIndex, 1) = lineKey
                didUpdateKeys = True
            End If

            If seen.Exists(lineKey) Then
                lineKey = NewStableKey()
                lineKeyValues(rowIndex, 1) = lineKey
                didUpdateKeys = True
            End If

            seen(lineKey) = True
            keys.Add lineKey
        End If
    Next rowIndex

    If didUpdateKeys Then
        lcLineKey.DataBodyRange.Resize(limit, 1).Value2 = lineKeyValues
    End If
End Function

Private Sub SeedRecordKeysByPosition(ByVal loInv As ListObject, _
                                      ByVal lcRecordKey As ListColumn, _
                                      ByVal recordKeys As Collection)

    If loInv.DataBodyRange Is Nothing Then Exit Sub
    If lcRecordKey Is Nothing Then Exit Sub

    Dim maxSeed As Long
    maxSeed = MinLong(loInv.ListRows.Count, recordKeys.Count)

    Dim rowIndex As Long
    For rowIndex = 1 To maxSeed
        If IsBlankLike(lcRecordKey.DataBodyRange.Cells(rowIndex, 1).Value2) Then
            lcRecordKey.DataBodyRange.Cells(rowIndex, 1).Value2 = CStr(recordKeys(rowIndex))
        End If
    Next rowIndex
End Sub

Private Function RecordKeysMatchTable(ByVal lcRecordKey As ListColumn, ByVal recordKeys As Collection) As Boolean
    If lcRecordKey Is Nothing Then Exit Function
    If lcRecordKey.DataBodyRange Is Nothing Then Exit Function

    Dim desiredRows As Long
    desiredRows = recordKeys.Count
    If desiredRows < 1 Then desiredRows = 1

    If lcRecordKey.DataBodyRange.Rows.Count <> desiredRows Then Exit Function

    If recordKeys.Count = 0 Then
        RecordKeysMatchTable = (Len(Trim$(CStr(lcRecordKey.DataBodyRange.Cells(1, 1).Value2))) = 0)
        Exit Function
    End If

    Dim i As Long
    For i = 1 To recordKeys.Count
        If CStr(lcRecordKey.DataBodyRange.Cells(i, 1).Value2) <> CStr(recordKeys(i)) Then Exit Function
    Next i

    RecordKeysMatchTable = True
End Function

Private Function SnapshotUserInputsByRecordKey(ByVal loInv As ListObject, _
                                                ByVal lcRecordKey As ListColumn, _
                                                ByVal userInputColumns As Collection) As Object

    Dim snapshot As Object
    Set snapshot = CreateObject("Scripting.Dictionary")

    If loInv.DataBodyRange Is Nothing Then
        Set SnapshotUserInputsByRecordKey = snapshot
        Exit Function
    End If

    If lcRecordKey Is Nothing Then
        Set SnapshotUserInputsByRecordKey = snapshot
        Exit Function
    End If

    Dim rowCount As Long
    rowCount = loInv.ListRows.Count
    If rowCount < 1 Then
        Set SnapshotUserInputsByRecordKey = snapshot
        Exit Function
    End If

    Dim keyValues As Variant
    keyValues = ColumnRangeValue2D(lcRecordKey.DataBodyRange, rowCount)

    Dim userColumnCount As Long
    userColumnCount = userInputColumns.Count

    Dim userColumnValues() As Variant
    If userColumnCount > 0 Then
        ReDim userColumnValues(1 To userColumnCount) As Variant

        Dim sourceColIndex As Long
        For sourceColIndex = 1 To userColumnCount
            Dim sourceLc As ListColumn
            Set sourceLc = userInputColumns(sourceColIndex)
            userColumnValues(sourceColIndex) = ColumnRangeValue2D(sourceLc.DataBodyRange, rowCount)
        Next sourceColIndex
    End If

    Dim rowIndex As Long
    For rowIndex = 1 To rowCount
        Dim keyValue As String
        keyValue = Trim$(CStr(keyValues(rowIndex, 1)))

        If Len(keyValue) > 0 Then
            If userColumnCount = 0 Then
                snapshot(keyValue) = Empty
            Else
                Dim rowValues() As Variant
                ReDim rowValues(1 To userColumnCount) As Variant

                Dim colIndex As Long
                For colIndex = 1 To userColumnCount
                    Dim colValues As Variant
                    colValues = userColumnValues(colIndex)
                    rowValues(colIndex) = colValues(rowIndex, 1)
                Next colIndex

                snapshot(keyValue) = rowValues
            End If
        End If
    Next rowIndex

    Set SnapshotUserInputsByRecordKey = snapshot
End Function

Private Function ColumnRangeValue2D(ByVal dataRange As Range, ByVal rowCount As Long) As Variant
    Dim values As Variant
    values = dataRange.Value2

    If rowCount = 1 Then
        Dim wrapped(1 To 1, 1 To 1) As Variant
        wrapped(1, 1) = values
        ColumnRangeValue2D = wrapped
    Else
        ColumnRangeValue2D = values
    End If
End Function

Private Sub ApplyRecordKeyRemap(ByVal loInv As ListObject, _
                                 ByVal lcRecordKey As ListColumn, _
                                 ByVal userInputColumns As Collection, _
                                 ByVal recordKeys As Collection, _
                                 ByVal oldValuesByKey As Object)

    If loInv.DataBodyRange Is Nothing Then Exit Sub
    If lcRecordKey Is Nothing Then Exit Sub

    If recordKeys.Count = 0 Then
        lcRecordKey.DataBodyRange.Cells(1, 1).ClearContents
        Exit Sub
    End If

    Dim rowCount As Long
    rowCount = loInv.ListRows.Count

    Dim keyOutput() As Variant
    ReDim keyOutput(1 To rowCount, 1 To 1) As Variant

    Dim rowIndex As Long
    For rowIndex = 1 To rowCount
        If rowIndex <= recordKeys.Count Then
            keyOutput(rowIndex, 1) = CStr(recordKeys(rowIndex))
        Else
            keyOutput(rowIndex, 1) = ""
        End If
    Next rowIndex

    lcRecordKey.DataBodyRange.Value2 = keyOutput

    Dim userColumnCount As Long
    userColumnCount = userInputColumns.Count
    If userColumnCount = 0 Then Exit Sub

    Dim colIndex As Long
    For colIndex = 1 To userColumnCount
        Dim lcUser As ListColumn
        Set lcUser = userInputColumns(colIndex)

        Dim columnOutput() As Variant
        ReDim columnOutput(1 To rowCount, 1 To 1) As Variant

        For rowIndex = 1 To rowCount
            Dim keyValue As String
            keyValue = CStr(keyOutput(rowIndex, 1))

            If Len(keyValue) > 0 And oldValuesByKey.Exists(keyValue) Then
                Dim rowValues As Variant
                rowValues = oldValuesByKey(keyValue)

                If IsArray(rowValues) Then
                    columnOutput(rowIndex, 1) = rowValues(colIndex)
                Else
                    columnOutput(rowIndex, 1) = Empty
                End If
            Else
                columnOutput(rowIndex, 1) = Empty
            End If
        Next rowIndex

        lcUser.DataBodyRange.Value2 = columnOutput
    Next colIndex
End Sub

Private Function RecordKeysMatchPrefix(ByVal lcRecordKey As ListColumn, _
                                        ByVal recordKeys As Collection, _
                                        ByVal prefixRows As Long) As Boolean

    If prefixRows <= 0 Then
        RecordKeysMatchPrefix = True
        Exit Function
    End If

    If lcRecordKey Is Nothing Then Exit Function
    If lcRecordKey.DataBodyRange Is Nothing Then Exit Function
    If lcRecordKey.DataBodyRange.Rows.Count < prefixRows Then Exit Function
    If recordKeys.Count < prefixRows Then Exit Function

    Dim rowIndex As Long
    For rowIndex = 1 To prefixRows
        If CStr(lcRecordKey.DataBodyRange.Cells(rowIndex, 1).Value2) <> CStr(recordKeys(rowIndex)) Then Exit Function
    Next rowIndex

    RecordKeysMatchPrefix = True
End Function

Private Sub ApplyRecordKeyAppend(ByVal loInv As ListObject, _
                                  ByVal lcRecordKey As ListColumn, _
                                  ByVal userInputColumns As Collection, _
                                  ByVal recordKeys As Collection, _
                                  ByVal startRow As Long, _
                                  ByVal endRow As Long)

    If lcRecordKey Is Nothing Then Exit Sub
    If loInv.DataBodyRange Is Nothing Then Exit Sub
    If startRow < 1 Or endRow < startRow Then Exit Sub

    Dim writeRows As Long
    writeRows = endRow - startRow + 1

    Dim keyOutput() As Variant
    ReDim keyOutput(1 To writeRows, 1 To 1) As Variant

    Dim offsetIx As Long
    For offsetIx = 1 To writeRows
        keyOutput(offsetIx, 1) = CStr(recordKeys(startRow + offsetIx - 1))
    Next offsetIx

    lcRecordKey.DataBodyRange.Cells(startRow, 1).Resize(writeRows, 1).Value2 = keyOutput

    If userInputColumns.Count > 0 Then
        Dim colIndex As Long
        For colIndex = 1 To userInputColumns.Count
            Dim lcUser As ListColumn
            Set lcUser = userInputColumns(colIndex)
            lcUser.DataBodyRange.Cells(startRow, 1).Resize(writeRows, 1).ClearContents
        Next colIndex
    End If
End Sub

Private Sub ClearUserInputRow(ByVal lo As ListObject, ByVal userInputColumns As Collection, ByVal rowIndex As Long)
    Dim colIndex As Long
    For colIndex = 1 To userInputColumns.Count
        Dim lcUser As ListColumn
        Set lcUser = userInputColumns(colIndex)
        lcUser.DataBodyRange.Cells(rowIndex, 1).ClearContents
    Next colIndex
End Sub

Private Function LastUsedLineNumberRowCount(ByVal lo As ListObject) As Long
    If lo.DataBodyRange Is Nothing Then Exit Function

    Dim lcLineNumber As ListColumn
    Set lcLineNumber = GetListColumn(lo, COL_LINE_NUMBER, "*Line Number")

    If lcLineNumber Is Nothing Then
        LastUsedLineNumberRowCount = LastUsedNonInternalConstantRowCountFallback(lo)
        Exit Function
    End If

    Dim rngLine As Range
    Set rngLine = lcLineNumber.DataBodyRange

    Dim rngConst As Range
    On Error Resume Next
    Set rngConst = rngLine.SpecialCells(xlCellTypeConstants)
    On Error GoTo 0
    If rngConst Is Nothing Then Exit Function

    Dim lastCell As Range
    Set lastCell = rngConst.Find(What:="*", LookIn:=xlValues, SearchOrder:=xlByRows, SearchDirection:=xlPrevious)
    If lastCell Is Nothing Then Exit Function

    LastUsedLineNumberRowCount = lastCell.Row - lo.DataBodyRange.Row + 1
End Function
Private Function LastNonInternalColumnIndex(ByVal lo As ListObject) As Long
    Dim c As Long
    For c = lo.ListColumns.Count To 1 Step -1
        If Not IsInternalHeader(CStr(lo.ListColumns(c).Name)) Then
            LastNonInternalColumnIndex = c
            Exit Function
        End If
    Next c
End Function

Private Function LastUsedNonInternalConstantRowCountFallback(ByVal lo As ListObject) As Long
    If lo.DataBodyRange Is Nothing Then Exit Function

    Dim lastCol As Long
    lastCol = LastNonInternalColumnIndex(lo)
    If lastCol < 1 Then Exit Function

    Dim rng As Range
    Set rng = lo.DataBodyRange.Resize(, lastCol)

    Dim rngConst As Range
    On Error Resume Next
    Set rngConst = rng.SpecialCells(xlCellTypeConstants)
    On Error GoTo 0
    If rngConst Is Nothing Then Exit Function

    Dim lastCell As Range
    Set lastCell = rngConst.Find(What:="*", LookIn:=xlValues, SearchOrder:=xlByRows, SearchDirection:=xlPrevious)
    If lastCell Is Nothing Then Exit Function

    LastUsedNonInternalConstantRowCountFallback = lastCell.Row - lo.DataBodyRange.Row + 1
End Function

Private Function RowHasAnyInput(ByVal inputColumns As Collection, ByVal rowIndex As Long) As Boolean
    Dim colIndex As Long
    For colIndex = 1 To inputColumns.Count
        Dim lc As ListColumn
        Set lc = inputColumns(colIndex)

        If Not IsBlankLike(lc.DataBodyRange.Cells(rowIndex, 1).Value2) Then
            RowHasAnyInput = True
            Exit Function
        End If
    Next colIndex
End Function

Private Function RowHasAnyInputExcludingColumn(ByVal inputColumns As Collection, _
                                               ByVal rowIndex As Long, _
                                               ByVal excludeColumnIndex As Long) As Boolean

    Dim colIndex As Long
    For colIndex = 1 To inputColumns.Count
        Dim lc As ListColumn
        Set lc = inputColumns(colIndex)

        If lc.Index <> excludeColumnIndex Then
            If Not IsBlankLike(lc.DataBodyRange.Cells(rowIndex, 1).Value2) Then
                RowHasAnyInputExcludingColumn = True
                Exit Function
            End If
        End If
    Next colIndex
End Function

Private Function GetUserInputColumns(ByVal lo As ListObject, _
                                     Optional ByVal skipInternalColumns As Boolean = True) As Collection

    Dim userInputColumns As New Collection
    Dim lc As ListColumn

    For Each lc In lo.ListColumns
        If Not (skipInternalColumns And IsInternalHeader(CStr(lc.Name))) Then
            If Not IsManagedFormulaColumn(lo.Name, CStr(lc.Name)) Then
                userInputColumns.Add lc
            End If
        End If
    Next lc

    Set GetUserInputColumns = userInputColumns
End Function

Public Sub AP_CompactLinesTable(Optional ByVal Silent As Boolean = True)
    Dim prevEvents As Boolean, prevScreen As Boolean, prevCalc As XlCalculation
    prevEvents = Application.EnableEvents
    prevScreen = Application.ScreenUpdating
    prevCalc = Application.Calculation

    On Error GoTo EH
    Application.EnableEvents = False
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    Dim usedRows As Long
    usedRows = LastUsedLineNumberRowCount(loLines)
    If usedRows < 1 Then usedRows = 1

    ResizeListObjectDataRows loLines, usedRows
    ApplyTableBottomBoundary loLines
    mLastKnownLinesTableRows = loLines.ListRows.Count

CleanExit:
    Application.Calculation = prevCalc
    Application.ScreenUpdating = prevScreen
    Application.EnableEvents = prevEvents
    Exit Sub

EH:
    If Not Silent Then
        MsgBox "AP_CompactLinesTable failed: " & Err.Description, vbExclamation
    End If
    Resume CleanExit
End Sub

Public Sub AP_CompactLinesSheetUsedRange(Optional ByVal Silent As Boolean = True, _
                                         Optional ByVal keepBufferRows As Long = -1)
    Dim prevEvents As Boolean, prevScreen As Boolean, prevCalc As XlCalculation
    prevEvents = Application.EnableEvents
    prevScreen = Application.ScreenUpdating
    prevCalc = Application.Calculation

    On Error GoTo EH
    Application.EnableEvents = False
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    If keepBufferRows < 0 Then keepBufferRows = LINES_BUFFER_ROWS

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    Dim keepBottomRow As Long
    keepBottomRow = loLines.Range.Row + loLines.Range.Rows.Count - 1 + keepBufferRows

    Dim usedBottomRow As Long
    usedBottomRow = wsLines.UsedRange.Row + wsLines.UsedRange.Rows.Count - 1

    If usedBottomRow > keepBottomRow Then
        wsLines.Rows((keepBottomRow + 1) & ":" & usedBottomRow).Clear
        wsLines.Rows((keepBottomRow + 1) & ":" & usedBottomRow).Delete
    End If

    Dim refreshedUsedRange As String
    refreshedUsedRange = wsLines.UsedRange.Address(False, False)
    TracePerf "compact lines used range=" & refreshedUsedRange

CleanExit:
    Application.Calculation = prevCalc
    Application.ScreenUpdating = prevScreen
    Application.EnableEvents = prevEvents
    Exit Sub

EH:
    If Not Silent Then
        MsgBox "AP_CompactLinesSheetUsedRange failed: " & Err.Description, vbExclamation
    End If
    Resume CleanExit
End Sub

Private Function GrowLinesTableRowTarget(ByVal requiredRows As Long) As Long
    Dim currentRows As Long
    currentRows = CurrentLinesTableRowCount()
    If currentRows < 1 Then currentRows = 1

    Dim targetRows As Long
    targetRows = requiredRows + LINES_BUFFER_ROWS

    If requiredRows > currentRows Then
        Dim growthRows As Long
        growthRows = currentRows \ 2
        If growthRows < LINES_GROW_CHUNK Then growthRows = LINES_GROW_CHUNK

        If targetRows < currentRows + growthRows Then
            targetRows = currentRows + growthRows
        End If
    End If

    If targetRows < requiredRows Then
        targetRows = requiredRows
    End If

    GrowLinesTableRowTarget = targetRows
End Function

Private Function GetUserInputColumnIndexes(ByVal lo As ListObject, ByVal excludeColumnIndex As Long) As Collection
    Dim indexes As New Collection
    Dim lc As ListColumn

    For Each lc In lo.ListColumns
        If lc.Index <> excludeColumnIndex Then
            If Not IsInternalHeader(CStr(lc.Name)) Then
                If Not IsManagedFormulaColumn(lo.Name, CStr(lc.Name)) Then
                    indexes.Add lc.Index
                End If
            End If
        End If
    Next lc

    Set GetUserInputColumnIndexes = indexes
End Function

Private Sub EnsureManagedSheetsCalculationEnabled()
    Dim wsLines As Worksheet
    Dim wsInv As Worksheet

    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)
    Set wsInv = ThisWorkbook.Worksheets(SH_RECORDS)

    On Error Resume Next
    If Not wsLines.EnableCalculation Then wsLines.EnableCalculation = True
    If Not wsInv.EnableCalculation Then wsInv.EnableCalculation = True
    On Error GoTo 0
End Sub

Private Sub DisableManagedSheetsCalculationForFastEdit()
    Dim wsLines As Worksheet
    Dim wsInv As Worksheet

    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)
    Set wsInv = ThisWorkbook.Worksheets(SH_RECORDS)

    On Error Resume Next
    Application.AutoCorrect.AutoFillFormulasInLists = True
    Application.AutoCorrect.AutoExpandListRange = True
    wsLines.EnableFormatConditionsCalculation = False

    If mHaveSavedLinesEnableCalculation Then
        wsLines.EnableCalculation = True
    Else
        wsLines.EnableCalculation = True
    End If

    If mHaveSavedRecordsEnableCalculation Then
        If CBool(mSavedRecordsEnableCalculation) Then wsInv.EnableCalculation = False
    Else
        wsInv.EnableCalculation = False
    End If
    On Error GoTo 0
End Sub

Private Function IsLinesSheetActive() As Boolean
    On Error Resume Next
    IsLinesSheetActive = (TypeName(ActiveSheet) = "Worksheet") And (ActiveSheet.Name = SH_LINES)
    On Error GoTo 0
End Function

Private Function CurrentLinesTableRowCount() As Long
    On Error GoTo SafeExit

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    CurrentLinesTableRowCount = loLines.ListRows.Count
    Exit Function

SafeExit:
    CurrentLinesTableRowCount = 0
End Function

Private Function IsManagedFormulaColumn(ByVal tableName As String, ByVal headerName As String) As Boolean
    Dim t As String
    Dim h As String

    t = LCase$(Trim$(tableName))
    h = LCase$(Trim$(headerName))

    Select Case t
        Case LCase$(TBL_LINES)
            Select Case h
                Case LCase$(COL_INV_ID_FORMULA), _
                     LCase$("*Line Type"), _
                     LCase$("Item Description"), _
                     LCase$("Distribution Combination"), _
                     LCase$("Accounting Date"), _
                     LCase$("Attribute Category"), _
                     LCase$("Attribute 1"), _
                     LCase$("Attribute 2"), _
                     LCase$("Attribute 3"), _
                     LCase$("Attribute 4"), _
                     LCase$("Attribute 5"), _
                     LCase$(COL_ATTR6_FORMULA), _
                     LCase$(COL_PROJECT_FORMULA), _
                     LCase$("Task Number"), _
                     LCase$("Expenditure Type"), _
                     LCase$("Expenditure Organization")
                    IsManagedFormulaColumn = True
                    Exit Function
            End Select

        Case LCase$(TBL_RECORDS)
            Select Case h
                Case LCase$("*Record ID"), _
                     LCase$("*Business Unit"), _
                     LCase$("*Source"), _
                     LCase$("*Record Number"), _
                     LCase$("*Record Amount"), _
                     LCase$("*Record Date"), _
                     LCase$("*Supplier Site"), _
                     LCase$("Record Currency"), _
                     LCase$("Payment Currency"), _
                     LCase$("Description"), _
                     LCase$("Import Set"), _
                     LCase$("*Record Type"), _
                     LCase$("Legal Entity"), _
                     LCase$("*Payment Terms"), _
                     LCase$("Record Received Date"), _
                     LCase$("Accounting Date"), _
                     LCase$("Payment Method"), _
                     LCase$("Pay Alone")
                    IsManagedFormulaColumn = True
                    Exit Function
            End Select
    End Select
End Function

Private Function IsInternalHeader(ByVal headerText As String) As Boolean
    Dim trimmedHeader As String
    trimmedHeader = LCase$(Trim$(headerText))

    IsInternalHeader = (Left$(trimmedHeader, 2) = "zz")
End Function

Private Function ChangeMayAffectRecords(ByVal changedBottomRow As Long, _
                                         ByVal changedTopRow As Long, _
                                         ByVal changedFirstCol As Long, _
                                         ByVal changedLastCol As Long, _
                                         ByVal protectChangedRows As Boolean) As Boolean
    ChangeMayAffectRecords = (changedTopRow > 0 And changedBottomRow >= changedTopRow)
End Function

Private Function IsLineStartValue(ByVal valueInCell As Variant) As Boolean
    If IsError(valueInCell) Then Exit Function
    If IsEmpty(valueInCell) Then Exit Function

    If IsNumeric(valueInCell) Then
        IsLineStartValue = (CDbl(valueInCell) = 1#)
    Else
        IsLineStartValue = (Trim$(CStr(valueInCell)) = "1")
    End If
End Function

Private Function NewStableKey() As String
    On Error Resume Next
    Dim guid As String
    guid = CStr(CreateObject("Scriptlet.TypeLib").GUID)
    On Error GoTo 0

    If Len(guid) >= 38 Then
        NewStableKey = Mid$(guid, 2, 36)
    Else
        EnsureRandomSeeded
        NewStableKey = Format$(Now, "yyyymmddhhnnss") & _
                       "-" & Right$("00000000" & Hex$(CLng(Rnd() * 2147483647#)), 8) & _
                       "-" & Right$("00000000" & Hex$(CLng(Rnd() * 2147483647#)), 8)
    End If
End Function

Private Sub EnsureRandomSeeded()
    If mRandomSeeded Then Exit Sub
    Randomize
    mRandomSeeded = True
End Sub

Private Function EnsureInternalColumn(ByVal lo As ListObject, ByVal headerName As String) As ListColumn
    Set EnsureInternalColumn = GetListColumn(lo, headerName)

    If EnsureInternalColumn Is Nothing Then
        Set EnsureInternalColumn = lo.ListColumns.Add
        EnsureInternalColumn.Name = headerName
    End If

    On Error Resume Next
    EnsureInternalColumn.Range.EntireColumn.Hidden = True
    On Error GoTo 0
End Function

Private Function GetListColumn(ByVal lo As ListObject, ParamArray colNames() As Variant) As ListColumn
    Dim i As Long

    For i = LBound(colNames) To UBound(colNames)
        On Error Resume Next
        Set GetListColumn = lo.ListColumns(CStr(colNames(i)))
        On Error GoTo 0

        If Not GetListColumn Is Nothing Then Exit Function
    Next i
End Function

Private Sub ResizeListObjectDataRows(ByVal lo As ListObject, ByVal newDataRows As Long)
    Dim totalRows As Long
    totalRows = 1 + newDataRows + IIf(lo.ShowTotals, 1, 0) 'header + data + totals(if any)

    Dim newRange As Range
    Set newRange = lo.Range.Cells(1, 1).Resize(totalRows, lo.Range.Columns.Count)

    lo.Resize newRange
End Sub

Private Sub ApplyListObjectRowFormatsFromPreviousRow(ByVal lo As ListObject, _
                                                     ByVal startRow As Long, _
                                                     ByVal endRow As Long)
    If lo Is Nothing Then Exit Sub
    If lo.DataBodyRange Is Nothing Then Exit Sub
    If startRow < 1 Then startRow = 1
    If endRow < startRow Then Exit Sub

    Dim rowCount As Long
    rowCount = lo.ListRows.Count
    If rowCount < 1 Then Exit Sub
    If startRow > rowCount Then Exit Sub
    If endRow > rowCount Then endRow = rowCount

    Dim templateRow As Long
    templateRow = startRow - 1
    If templateRow < 1 Then templateRow = 1
    If templateRow > rowCount Then templateRow = rowCount

    On Error Resume Next
    lo.DataBodyRange.Rows(templateRow).Copy
    lo.DataBodyRange.Rows(startRow & ":" & endRow).PasteSpecial Paste:=xlPasteFormats
    Application.CutCopyMode = False
    On Error GoTo 0

    Dim targetRow As Long
    For targetRow = startRow To endRow
        CopyListObjectRowBorders lo, templateRow, targetRow
    Next targetRow
End Sub

Private Sub CopyListObjectRowBorders(ByVal lo As ListObject, _
                                     ByVal sourceRow As Long, _
                                     ByVal targetRow As Long)
    If lo Is Nothing Then Exit Sub
    If lo.DataBodyRange Is Nothing Then Exit Sub
    If sourceRow < 1 Or targetRow < 1 Then Exit Sub
    If sourceRow > lo.ListRows.Count Or targetRow > lo.ListRows.Count Then Exit Sub

    Dim colIndex As Long
    For colIndex = 1 To lo.ListColumns.Count
        CopyCellBorderStyles lo.DataBodyRange.Cells(sourceRow, colIndex), _
                             lo.DataBodyRange.Cells(targetRow, colIndex)
    Next colIndex
End Sub

Private Sub ApplyRecordNumberBordersFromPreviousRow(ByVal loInv As ListObject, _
                                                     ByVal startRow As Long, _
                                                     ByVal endRow As Long)
    If loInv Is Nothing Then Exit Sub
    If startRow < 2 Then Exit Sub
    If endRow < startRow Then Exit Sub

    Dim recordNumberColumn As ListColumn
    Set recordNumberColumn = GetListColumn(loInv, COL_INV_NUMBER_FORMULA)
    If recordNumberColumn Is Nothing Then Exit Sub
    If recordNumberColumn.DataBodyRange Is Nothing Then Exit Sub

    If endRow > recordNumberColumn.DataBodyRange.Rows.Count Then
        endRow = recordNumberColumn.DataBodyRange.Rows.Count
    End If

    Dim rowIndex As Long
    For rowIndex = startRow To endRow
        CopyCellBorderStyles recordNumberColumn.DataBodyRange.Cells(rowIndex - 1, 1), _
                             recordNumberColumn.DataBodyRange.Cells(rowIndex, 1)
    Next rowIndex
End Sub

Private Sub CopyCellBorderStyles(ByVal sourceCell As Range, ByVal targetCell As Range)
    Dim borderIds As Variant
    borderIds = Array(xlEdgeLeft, xlEdgeTop, xlEdgeBottom, xlEdgeRight)

    Dim idx As Long
    For idx = LBound(borderIds) To UBound(borderIds)
        Dim borderId As Variant
        borderId = borderIds(idx)

        With targetCell.Borders(borderId)
            .LineStyle = sourceCell.Borders(borderId).LineStyle
            .Weight = sourceCell.Borders(borderId).Weight
            .Color = sourceCell.Borders(borderId).Color
        End With
    Next idx
End Sub

Private Sub ClearOrphanedTableArea(ByVal ws As Worksheet, _
                                   ByVal startRow As Long, _
                                   ByVal endRow As Long, _
                                   ByVal firstCol As Long, _
                                   ByVal colCount As Long, _
                                   Optional ByVal keepFormats As Boolean = True)

    If endRow < startRow Then Exit Sub

    Dim rngClear As Range
    Set rngClear = ws.Range(ws.Cells(startRow, firstCol), _
                            ws.Cells(endRow, firstCol + colCount - 1))

    If keepFormats Then
        'Clear formulas/values only; leave formatting as-is.
        rngClear.ClearContents
    Else
        'Clear all contents/formatting to prevent table style carryover below table.
        rngClear.Clear
    End If
End Sub

Private Sub CalculateTouchedTables(ByVal includeRecords As Boolean, Optional ByVal includeLines As Boolean = True)
    On Error Resume Next

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    If includeLines Then
        If Not loLines.DataBodyRange Is Nothing Then
            loLines.DataBodyRange.Calculate
        End If
    End If

    If includeRecords Then
        Dim wsInv As Worksheet
        Set wsInv = ThisWorkbook.Worksheets(SH_RECORDS)

        Dim loInv As ListObject
        Set loInv = wsInv.ListObjects(TBL_RECORDS)

        RecalculateRecordTable loInv
    End If

    On Error GoTo 0
End Sub

Private Sub CalculateTouchedLineTableSlice(ByVal changedTopRow As Long, _
                                           ByVal changedBottomRow As Long, _
                                           Optional ByVal includeLines As Boolean = True)
    If Not includeLines Then Exit Sub

    On Error Resume Next

    Dim wsLines As Worksheet
    Set wsLines = ThisWorkbook.Worksheets(SH_LINES)

    Dim loLines As ListObject
    Set loLines = wsLines.ListObjects(TBL_LINES)

    CalculateLineFormulaSlice loLines, changedTopRow, changedBottomRow, (changedTopRow > 0 And changedBottomRow >= changedTopRow)

    On Error GoTo 0
End Sub

Private Sub CalculateLineFormulaSlice(ByVal loLines As ListObject, _
                                      ByVal changedTopRow As Long, _
                                      ByVal changedBottomRow As Long, _
                                      ByVal useTargetSlice As Boolean)
    If loLines Is Nothing Then Exit Sub
    If loLines.DataBodyRange Is Nothing Then Exit Sub

    If Not useTargetSlice Then
        loLines.DataBodyRange.Calculate
        Exit Sub
    End If

    Dim usedRows As Long
    usedRows = LastUsedLineNumberRowCount(loLines)
    If usedRows < 1 Then usedRows = 1

    Dim startIx As Long
    Dim endIx As Long
    ResolveLineSliceBounds loLines, usedRows, changedTopRow, changedBottomRow, True, startIx, endIx
    If endIx < startIx Then Exit Sub

    loLines.DataBodyRange.Rows(startIx & ":" & endIx).Calculate
End Sub

Private Sub ResolveLineSliceBounds(ByVal loLines As ListObject, _
                                   ByVal usedRows As Long, _
                                   ByVal changedTopRow As Long, _
                                   ByVal changedBottomRow As Long, _
                                   ByVal useTargetSlice As Boolean, _
                                   ByRef startIx As Long, _
                                   ByRef endIx As Long)
    startIx = 1
    endIx = usedRows

    If Not useTargetSlice Then Exit Sub

    Dim firstDataRow As Long
    firstDataRow = loLines.DataBodyRange.Row

    startIx = changedTopRow - firstDataRow + 1
    endIx = changedBottomRow - firstDataRow + 1

    If startIx < 1 Then startIx = 1
    If endIx > usedRows Then endIx = usedRows
End Sub

Private Function ElapsedTimerSeconds(ByVal startValue As Double) As Double
    Dim currentValue As Double
    currentValue = Timer

    If currentValue < startValue Then
        currentValue = currentValue + 86400#
    End If

    ElapsedTimerSeconds = currentValue - startValue
End Function

Private Sub TracePerf(ByVal message As String)
    Debug.Print Format$(Now, "yyyy-mm-dd hh:nn:ss"); " | APPerf | "; message
End Sub

Private Function RangeHasAnyContent(ByVal ws As Worksheet, _
                                    ByVal topRow As Long, _
                                    ByVal bottomRow As Long, _
                                    ByVal leftCol As Long, _
                                    ByVal rightCol As Long) As Boolean

    If topRow <= 0 Or bottomRow < topRow Then Exit Function
    If leftCol <= 0 Or rightCol < leftCol Then Exit Function
    If topRow > ws.Rows.Count Or leftCol > ws.Columns.Count Then Exit Function

    If bottomRow > ws.Rows.Count Then bottomRow = ws.Rows.Count
    If rightCol > ws.Columns.Count Then rightCol = ws.Columns.Count

    Dim rngCheck As Range
    Set rngCheck = ws.Range(ws.Cells(topRow, leftCol), ws.Cells(bottomRow, rightCol))

    RangeHasAnyContent = (Application.CountA(rngCheck) > 0)
End Function

Private Function IsBlankLike(ByVal valueInCell As Variant) As Boolean
    If IsError(valueInCell) Then
        IsBlankLike = False
        Exit Function
    End If

    If IsEmpty(valueInCell) Then
        IsBlankLike = True
        Exit Function
    End If

    IsBlankLike = (Len(Trim$(CStr(valueInCell))) = 0)
End Function

Private Function MaxLong(ByVal firstValue As Long, ByVal secondValue As Long) As Long
    If firstValue >= secondValue Then
        MaxLong = firstValue
    Else
        MaxLong = secondValue
    End If
End Function

Private Function MinLong(ByVal firstValue As Long, ByVal secondValue As Long) As Long
    If firstValue <= secondValue Then
        MinLong = firstValue
    Else
        MinLong = secondValue
    End If
End Function

Private Sub ApplyTableBottomBoundary(ByVal lo As ListObject)
    Dim edge As Border
    Set edge = lo.Range.Borders(xlEdgeBottom)

    edge.LineStyle = xlContinuous
    edge.Weight = xlThin
    edge.Color = RGB(128, 128, 128)
End Sub


