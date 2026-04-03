Option Explicit

Private Sub Worksheet_Activate()
    On Error Resume Next
    AP_SetPerformanceEditMode True
    On Error GoTo 0
End Sub

Private Sub Worksheet_Deactivate()
    On Error Resume Next
    AP_HandleLinesSheetDeactivate True
    On Error GoTo 0
End Sub

Private Sub Worksheet_Change(ByVal Target As Range)
    On Error GoTo SafeExit
    If Not Application.EnableEvents Then Exit Sub

    Dim lo As ListObject
    Set lo = Me.ListObjects("tbl_invoice_lines")

    Dim firstCol As Long, lastCol As Long
    firstCol = lo.Range.Column
    lastCol = firstCol + lo.Range.Columns.Count - 1

    Dim tableTopRow As Long
    tableTopRow = lo.HeaderRowRange.Row

    Dim watchRng As Range
    Set watchRng = Me.Range(Me.Cells(tableTopRow, firstCol), Me.Cells(Me.Rows.Count, lastCol))

    Dim effectiveTarget As Range
    Set effectiveTarget = Intersect(Target, watchRng)
    If effectiveTarget Is Nothing Then Exit Sub

    Dim changedBottomRow As Long
    Dim changedTopRow As Long
    Dim changedFirstCol As Long
    Dim changedLastCol As Long

    changedTopRow = effectiveTarget.Row
    changedBottomRow = effectiveTarget.Row + effectiveTarget.Rows.Count - 1
    changedFirstCol = effectiveTarget.Column
    changedLastCol = effectiveTarget.Column + effectiveTarget.Columns.Count - 1

    If changedFirstCol < firstCol Then changedFirstCol = firstCol
    If changedLastCol > lastCol Then changedLastCol = lastCol
    If changedFirstCol > changedLastCol Then
        changedFirstCol = firstCol
        changedLastCol = lastCol
    End If

    Dim protectChangedRows As Boolean
    If lo.DataBodyRange Is Nothing Then
        protectChangedRows = True
    Else
        protectChangedRows = (Intersect(effectiveTarget, lo.DataBodyRange) Is Nothing)
    End If

    AP_QueueSyncAll_WithTarget True, changedBottomRow, changedTopRow, changedFirstCol, changedLastCol, protectChangedRows
    Application.OnUndo "Undo last invoice-lines change", "'" & ThisWorkbook.Name & "'!AP_UndoInvoiceLinesChange"

SafeExit:
End Sub
