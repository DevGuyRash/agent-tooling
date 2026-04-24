Option Explicit

'==========================================================
' PURPOSE
'   1) Export Worksheet(2) -> ApRecordsInterface.csv
'   2) Export Worksheet(3) -> ApRecordLinesInterface.csv
'   3) Zip them into a user-selected ZIP file (filenames locked)
'
'   ZIP creation is done in a production-safe way:
'     - Primary: PowerShell + .NET ZipFile (synchronous, reliable, no Shell caching)
'     - Fallback: Shell.Application ZIP (best-effort, with robust waits)
'
'   Newlines: ALL newline characters are SQUASHED (removed), not converted to "\n".
'==========================================================

'========================
' API DECLARATIONS
'========================
#If VBA7 Then
    Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
    Private Declare PtrSafe Function OpenClipboard Lib "user32" (ByVal hwnd As LongPtr) As Long
    Private Declare PtrSafe Function EmptyClipboard Lib "user32" () As Long
    Private Declare PtrSafe Function CloseClipboard Lib "user32" () As Long
    Private Declare PtrSafe Function SetClipboardData Lib "user32" (ByVal uFormat As Long, ByVal hMem As LongPtr) As LongPtr
    Private Declare PtrSafe Function GlobalAlloc Lib "kernel32" (ByVal wFlags As Long, ByVal dwBytes As LongPtr) As LongPtr
    Private Declare PtrSafe Function GlobalLock Lib "kernel32" (ByVal hMem As LongPtr) As LongPtr
    Private Declare PtrSafe Function GlobalUnlock Lib "kernel32" (ByVal hMem As LongPtr) As Long
    Private Declare PtrSafe Function GlobalFree Lib "kernel32" (ByVal hMem As LongPtr) As LongPtr
    Private Declare PtrSafe Function lstrcpyW Lib "kernel32" (ByVal lpString1 As LongPtr, ByVal lpString2 As LongPtr) As LongPtr
#Else
    Private Declare Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
    Private Declare Function OpenClipboard Lib "user32" (ByVal hwnd As Long) As Long
    Private Declare Function EmptyClipboard Lib "user32" () As Long
    Private Declare Function CloseClipboard Lib "user32" () As Long
    Private Declare Function SetClipboardData Lib "user32" (ByVal uFormat As Long, ByVal hMem As Long) As Long
    Private Declare Function GlobalAlloc Lib "kernel32" (ByVal wFlags As Long, ByVal dwBytes As Long) As Long
    Private Declare Function GlobalLock Lib "kernel32" (ByVal hMem As Long) As Long
    Private Declare Function GlobalUnlock Lib "kernel32" (ByVal hMem As Long) As Long
    Private Declare Function GlobalFree Lib "kernel32" (ByVal hMem As Long) As Long
    Private Declare Function lstrcpyW Lib "kernel32" (ByVal lpString1 As Long, ByVal lpString2 As Long) As Long
#End If

'========================
' CONFIG
'========================
Private Const HEADER_ROW As Long = 4
Private Const FIRST_DATA_ROW As Long = 5

Private Const CSV_INV As String = "ApRecordsInterface.csv"
Private Const CSV_LINES As String = "ApRecordLinesInterface.csv"

' ZIP behavior (fallback Shell method)
Private Const ZIP_NS_TIMEOUT_SEC As Double = 10#
Private Const ZIP_ADD_TIMEOUT_SEC As Double = 180#
Private Const ZIP_POLL_SLEEP_MS As Long = 150

' PowerShell zip script name (created in temp folder and deleted)
Private Const PS_SCRIPT_NAME As String = "aprecordimport_makezip.ps1"
Private Const WORK_ZIP_NAME As String = "aprecordimport.zip"
Private Const GMEM_MOVEABLE As Long = &H2
Private Const CF_UNICODETEXT As Long = 13

' Which tabs to export (skip first two tabs)
Private Const RECORDS_SHEET_NAME As String = "DATA_RECORDS"
Private Const LINES_SHEET_NAME As String = "DATA_RECORD_LINES"
Private Const RECORDS_TABLE_NAME As String = "tbl_records"
Private Const RECORDS_SHEET_INDEX As Long = 3
Private Const LINES_SHEET_INDEX As Long = 4

'========================
' APP STATE
'========================
Private Type TAppState
    ScreenUpdating  As Boolean
    EnableEvents    As Boolean
    DisplayAlerts   As Boolean
    Calculation     As XlCalculation
    StatusBar       As Variant
    EnableCancelKey As XlEnableCancelKey
End Type

Private mRandomSeeded As Boolean

'========================
' MAIN
'========================
Public Sub GenCSV()
    Dim zipPathV As Variant

    zipPathV = Application.GetSaveAsFilename( _
                    InitialFileName:="aprecordimport", _
                    FileFilter:="Zip Files (*.zip), *.zip", _
                    Title:="Please select a location and file name for ZIP File")

    If zipPathV = False Then GoTo CleanExit
    GenCSV_ToPath EnsureExtension(CStr(zipPathV), ".zip"), True

CleanExit:
End Sub

Public Sub GenCSV_ToPath(ByVal zipPath As String, Optional ByVal ShowSuccessMessage As Boolean = True)

    Dim wb As Workbook
    Set wb = ActiveWorkbook

    Dim st As TAppState
    SaveAppState st
    OptimizeForSpeed True, st
    Application.EnableCancelKey = xlErrorHandler

    Dim tempFolder As String
    Dim csvInvPath As String, csvLinesPath As String
    Dim workZipPath As String
    Dim psScriptPath As String

    On Error GoTo ErrHandler

    Application.Run "'" & ThisWorkbook.Name & "'!AP_BeforeExportFlush", True

    Dim recordsWs As Worksheet
    Dim linesWs As Worksheet

    Set recordsWs = ResolveSourceWorksheet(wb, RECORDS_SHEET_NAME, RECORDS_SHEET_INDEX)
    Set linesWs = ResolveSourceWorksheet(wb, LINES_SHEET_NAME, LINES_SHEET_INDEX)

    If recordsWs Is Nothing Or linesWs Is Nothing Then
        Err.Raise vbObjectError + 2000, "GenCSV", _
                "Unable to resolve export sheets." & vbCrLf & _
                "Expected names first: '" & RECORDS_SHEET_NAME & "' and '" & LINES_SHEET_NAME & "'." & vbCrLf & _
                "Fallback indexes: " & RECORDS_SHEET_INDEX & " and " & LINES_SHEET_INDEX & "."
    End If

    zipPath = EnsureExtension(zipPath, ".zip")
    EnsureParentFolderExistsOrRaise zipPath
    DeleteFileIfExistsOrRaise zipPath, _
        "Unable to overwrite existing ZIP. Close Explorer preview panes / apps using it and try again."

    tempFolder = CreateTempFolder("aprecordimport_")
    csvInvPath = tempFolder & Application.PathSeparator & CSV_INV
    csvLinesPath = tempFolder & Application.PathSeparator & CSV_LINES
    workZipPath = tempFolder & Application.PathSeparator & WORK_ZIP_NAME
    psScriptPath = tempFolder & Application.PathSeparator & PS_SCRIPT_NAME

    WriteWorksheetToInterfaceCsv recordsWs, csvInvPath
    WriteWorksheetToInterfaceCsv linesWs, csvLinesPath
    CreateZipFromTwoFiles workZipPath, csvInvPath, CSV_INV, csvLinesPath, CSV_LINES, psScriptPath
    CopyFileOverwrite workZipPath, zipPath
    EnsureCreatedFileExists zipPath, "Expected final ZIP output was not created."

    Dim importSets As Collection
    Set importSets = CollectUniqueImportSets(recordsWs)

    Dim clipboardCopied As Boolean
    If importSets.Count = 1 Then
        clipboardCopied = TrySetClipboardText(CStr(importSets.Item(1)))
    End If

    If ShowSuccessMessage Then
        MsgBox BuildExportSuccessMessage(zipPath, importSets, clipboardCopied), vbInformation
    End If

CleanExit:
    On Error Resume Next
    If Len(psScriptPath) > 0 Then Kill psScriptPath
    If Len(workZipPath) > 0 Then Kill workZipPath
    If Len(csvInvPath) > 0 Then Kill csvInvPath
    If Len(csvLinesPath) > 0 Then Kill csvLinesPath
    If Len(tempFolder) > 0 Then RmDir tempFolder
    On Error GoTo 0

    OptimizeForSpeed False, st
    Exit Sub

ErrHandler:
    If Err.Number = 18 Then
        Resume CleanExit
    Else
        MsgBox "ERROR: " & Err.Number & vbCrLf & Err.Description, vbCritical
        Resume CleanExit
    End If

End Sub

Private Function CollectUniqueImportSets(ByVal recordsWs As Worksheet) As Collection
    Dim values As New Collection
    Dim seen As Object
    Set seen = CreateObject("Scripting.Dictionary")

    Dim lo As ListObject
    On Error Resume Next
    Set lo = recordsWs.ListObjects(RECORDS_TABLE_NAME)
    On Error GoTo 0
    If lo Is Nothing Then
        Set CollectUniqueImportSets = values
        Exit Function
    End If

    Dim lc As ListColumn
    On Error Resume Next
    Set lc = lo.ListColumns("Import Set")
    On Error GoTo 0
    If lc Is Nothing Then
        Set CollectUniqueImportSets = values
        Exit Function
    End If
    If lc.DataBodyRange Is Nothing Then
        Set CollectUniqueImportSets = values
        Exit Function
    End If

    Dim cell As Range
    For Each cell In lc.DataBodyRange.Cells
        Dim textValue As String
        textValue = Trim$(CStr(cell.Value2))
        If Len(textValue) > 0 Then
            If Not seen.Exists(textValue) Then
                seen(textValue) = True
                values.Add textValue
            End If
        End If
    Next cell

    Set CollectUniqueImportSets = values
End Function

Private Function BuildExportSuccessMessage(ByVal zipPath As String, _
                                           ByVal importSets As Collection, _
                                           ByVal clipboardCopied As Boolean) As String
    Dim messageText As String
    messageText = "ZIP created successfully:" & vbCrLf & zipPath

    If importSets.Count = 0 Then
        messageText = messageText & vbCrLf & vbCrLf & "Import Set: none found."
    ElseIf importSets.Count = 1 Then
        messageText = messageText & vbCrLf & vbCrLf & "Import Set:" & vbCrLf & CStr(importSets.Item(1))
        If clipboardCopied Then
            messageText = messageText & vbCrLf & vbCrLf & "Copied to clipboard."
        Else
            messageText = messageText & vbCrLf & vbCrLf & "Clipboard copy failed."
        End If
    Else
        messageText = messageText & vbCrLf & vbCrLf & "Import Sets:" & vbCrLf & JoinCollection(importSets, vbCrLf)
        messageText = messageText & vbCrLf & vbCrLf & "Multiple unique import sets found, so nothing was copied to the clipboard."
    End If

    BuildExportSuccessMessage = messageText
End Function

Private Function JoinCollection(ByVal values As Collection, ByVal delimiter As String) As String
    Dim i As Long
    For i = 1 To values.Count
        If i > 1 Then JoinCollection = JoinCollection & delimiter
        JoinCollection = JoinCollection & CStr(values.Item(i))
    Next i
End Function

Private Function TrySetClipboardText(ByVal textValue As String) As Boolean
    On Error Resume Next

    If TrySetClipboardTextWinApi(textValue) Then
        TrySetClipboardText = True
        Exit Function
    End If

    Dim htmlDoc As Object
    Set htmlDoc = CreateObject("htmlfile")
    If Not htmlDoc Is Nothing Then
        htmlDoc.ParentWindow.ClipboardData.SetData "text", textValue
        If Err.Number = 0 Then
            TrySetClipboardText = True
            Exit Function
        End If
    End If

    Err.Clear

    Dim tempFolder As String
    Dim tempPath As String
    tempFolder = CreateTempFolder("ap_clip_")
    tempPath = tempFolder & Application.PathSeparator & "clipboard.txt"

    Dim ff As Integer
    ff = FreeFile
    Open tempPath For Binary Access Write As #ff
    Put #ff, 1, textValue
    Close #ff

    Dim shell As Object
    Set shell = CreateObject("WScript.Shell")

    Dim cmd As String
    cmd = "powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -Command " & _
          QuoteArg("Set-Clipboard -Value ([System.IO.File]::ReadAllText('" & Replace(tempPath, "'", "''") & "'))")

    Dim exitCode As Long
    exitCode = shell.Run(cmd, 0, True)

    If Err.Number = 0 And exitCode = 0 Then
        TrySetClipboardText = True
        GoTo Cleanup
    End If

    Err.Clear

    cmd = "cmd.exe /c type " & QuoteArg(tempPath) & " | clip"
    exitCode = shell.Run(cmd, 0, True)

    If Err.Number = 0 And exitCode = 0 Then
        TrySetClipboardText = True
    End If

Cleanup:
    On Error Resume Next
    Kill tempPath
    RmDir tempFolder
    On Error GoTo 0
End Function

Private Function TrySetClipboardTextWinApi(ByVal textValue As String) As Boolean
    Dim textWithNull As String
    textWithNull = textValue & vbNullChar

#If VBA7 Then
    Dim hMem As LongPtr
    Dim pMem As LongPtr
#Else
    Dim hMem As Long
    Dim pMem As Long
#End If

    hMem = GlobalAlloc(GMEM_MOVEABLE, LenB(textWithNull))
    If hMem = 0 Then Exit Function

    pMem = GlobalLock(hMem)
    If pMem = 0 Then GoTo Cleanup

    lstrcpyW pMem, StrPtr(textWithNull)
    GlobalUnlock hMem

    Dim openAttempt As Long
    For openAttempt = 1 To 10
        If OpenClipboard(Application.Hwnd) <> 0 Then Exit For
        Sleep 50
    Next openAttempt
    If openAttempt > 10 Then GoTo Cleanup

    If EmptyClipboard() = 0 Then GoTo CloseHandle
    If SetClipboardData(CF_UNICODETEXT, hMem) = 0 Then GoTo CloseHandle

    TrySetClipboardTextWinApi = True
    hMem = 0

CloseHandle:
    CloseClipboard

Cleanup:
    If hMem <> 0 Then
        GlobalFree hMem
    End If
End Function

'==========================================================
' CSV EXPORT (values-only, preserves formatting, trims, END)
'==========================================================
Private Sub WriteWorksheetToInterfaceCsv(ByVal ws As Worksheet, ByVal csvPath As String)

    Dim lastCol As Long
    lastCol = LastColumnInRow(ws, HEADER_ROW)
    If lastCol = 0 Then
        CreateEmptyFile csvPath
        Exit Sub
    End If

    Dim lastRow As Long
    lastRow = LastDataRowInColumns(ws, FIRST_DATA_ROW, lastCol)
    If lastRow < FIRST_DATA_ROW Then
        CreateEmptyFile csvPath
        Exit Sub
    End If

    Dim rowCount As Long
    rowCount = lastRow - FIRST_DATA_ROW + 1

    Dim hdr As Variant
    hdr = ws.Range(ws.Cells(HEADER_ROW, 1), ws.Cells(HEADER_ROW, lastCol)).Value2

    Dim exportColumns As Collection
    Set exportColumns = BuildExportColumnMap(hdr, lastCol)

    Dim exportColCount As Long
    exportColCount = exportColumns.Count
    If exportColCount = 0 Then
        CreateEmptyFile csvPath
        Exit Sub
    End If

    ' Date columns by header name (Oracle control file expects YYYY/MM/DD for these)
    Dim isDateCol() As Boolean
    ReDim isDateCol(1 To exportColCount) As Boolean

    Dim exportIndex As Long
    For exportIndex = 1 To exportColCount
        Dim sourceCol As Long
        sourceCol = CLng(exportColumns(exportIndex))

        Dim h As String
        h = CleanCellString(CStr(hdr(1, sourceCol)))
        isDateCol(exportIndex) = (InStr(1, UCase$(h), "DATE", vbBinaryCompare) > 0)
    Next exportIndex

    ' Read values fast
    Dim dataRng As Range
    Set dataRng = ws.Range(ws.Cells(FIRST_DATA_ROW, 1), ws.Cells(lastRow, lastCol))

    Dim vals As Variant
    vals = dataRng.Value2

    ' Pre-clean string values in the array (fast)
    Dim r As Long
    Dim c As Long
    For r = 1 To rowCount
        For c = 1 To lastCol
            If IsError(vals(r, c)) Then
                Err.Raise vbObjectError + 2100, "GenCSV", _
                          "Excel error value found in sheet '" & ws.Name & "' at row " & (FIRST_DATA_ROW + r - 1) & _
                          ", col " & c & ". Fix #REF!/#VALUE!/etc. before exporting."
            End If

            If VarType(vals(r, c)) = vbString Then
                vals(r, c) = CleanCellString(CStr(vals(r, c)))
            End If
        Next c
    Next r

    ' Cache column formats when uniform (speed). If mixed, we fall back per-cell.
    Dim colFmt As Variant
    Dim colFmtIsUniform() As Boolean
    Dim colFmtStr() As String
    ReDim colFmtIsUniform(1 To exportColCount) As Boolean
    ReDim colFmtStr(1 To exportColCount) As String

    For exportIndex = 1 To exportColCount
        sourceCol = CLng(exportColumns(exportIndex))

        colFmt = ws.Range(ws.Cells(FIRST_DATA_ROW, sourceCol), ws.Cells(lastRow, sourceCol)).NumberFormat
        If IsNull(colFmt) Then
            colFmtIsUniform(exportIndex) = False
            colFmtStr(exportIndex) = vbNullString
        Else
            colFmtIsUniform(exportIndex) = True
            colFmtStr(exportIndex) = CStr(colFmt)
        End If
    Next exportIndex

    ' Write CSV as UTF-8 (no BOM)
    Dim textStream As Object, binStream As Object
    Set textStream = CreateObject("ADODB.Stream")
    textStream.Type = 2
    textStream.Charset = "UTF-8"
    textStream.Open

    Dim fields() As String
    ReDim fields(1 To exportColCount + 1) As String ' + END

    For r = 1 To rowCount
        Dim rowHasAny As Boolean
        rowHasAny = False

        For exportIndex = 1 To exportColCount
            sourceCol = CLng(exportColumns(exportIndex))

            Dim s As String
            s = ValueToExportString(ws, vals(r, sourceCol), isDateCol(exportIndex), _
                                    colFmtIsUniform(exportIndex), colFmtStr(exportIndex), _
                                    FIRST_DATA_ROW + r - 1, sourceCol)

            fields(exportIndex) = CsvEscape(s)
            If Len(s) > 0 Then rowHasAny = True
        Next exportIndex

        If rowHasAny Then
            fields(exportColCount + 1) = "END" ' final marker
            textStream.WriteText Join(fields, ",") & vbLf
        End If
    Next r

    ' Strip BOM (skip first 3 bytes)
    If textStream.Size >= 3 Then
        textStream.Position = 3
    Else
        textStream.Position = 0
    End If

    Set binStream = CreateObject("ADODB.Stream")
    binStream.Type = 1
    binStream.Open

    textStream.CopyTo binStream
    binStream.SaveToFile csvPath, 2

    binStream.Close
    textStream.Close

End Sub

Private Function BuildExportColumnMap(ByVal hdr As Variant, ByVal lastCol As Long) As Collection
    Dim exportColumns As New Collection

    Dim c As Long
    For c = 1 To lastCol
        Dim headerText As String
        headerText = CleanCellString(CStr(hdr(1, c)))

        If Not HeaderIsInternal(headerText) Then
            exportColumns.Add c
        End If
    Next c

    Set BuildExportColumnMap = exportColumns
End Function

Private Function HeaderIsInternal(ByVal headerText As String) As Boolean
    Dim trimmedHeader As String
    trimmedHeader = LCase$(Trim$(headerText))

    ' Internal helper columns are prefixed with zz (e.g. zzLineKey, zzRecordKey).
    HeaderIsInternal = (Left$(trimmedHeader, 2) = "zz")
End Function

Private Function ResolveSourceWorksheet(ByVal wb As Workbook, ByVal preferredSheetName As String, ByVal fallbackSheetIndex As Long) As Worksheet
    Set ResolveSourceWorksheet = WorksheetByName(wb, preferredSheetName)

    If ResolveSourceWorksheet Is Nothing Then
        If wb.Worksheets.Count >= fallbackSheetIndex Then
            Set ResolveSourceWorksheet = wb.Worksheets(fallbackSheetIndex)
        End If
    End If
End Function

Private Function WorksheetByName(ByVal wb As Workbook, ByVal sheetName As String) As Worksheet
    On Error Resume Next
    Set WorksheetByName = wb.Worksheets(sheetName)
    On Error GoTo 0
End Function

Private Function ValueToExportString(ByVal ws As Worksheet, ByVal v As Variant, ByVal isDateColumn As Boolean, _
                                    ByVal fmtUniform As Boolean, ByVal fmtString As String, _
                                    ByVal sheetRow As Long, ByVal sheetCol As Long) As String

    If IsEmpty(v) Then
        ValueToExportString = ""
        Exit Function
    End If

    If VarType(v) = vbString Then
        Dim t As String
        t = CStr(v)
        If isDateColumn And Len(t) > 0 Then
            t = NormalizeDateStringYMD(t, ws.Name, sheetRow, sheetCol)
        End If
        ValueToExportString = t
        Exit Function
    End If

    If VarType(v) = vbBoolean Then
        ValueToExportString = IIf(CBool(v), "TRUE", "FALSE")
        Exit Function
    End If

    ' Numeric/Date serials
    If isDateColumn Then
        ValueToExportString = Format$(ExcelSerialToDate(CDbl(v), ws.Parent.Date1904), "yyyy/mm/dd")
        Exit Function
    End If

    ' Preserve numeric formatting without relying on cell width.
    Dim outS As String
    If fmtUniform Then
        outS = SafeExcelText(v, fmtString, CStr(v))
    Else
        outS = SafeExcelText(v, ws.Cells(sheetRow, sheetCol).NumberFormat, CStr(v))
    End If

    ValueToExportString = CleanCellString(outS)

End Function

Private Function SafeExcelText(ByVal v As Variant, ByVal fmt As String, ByVal fallback As String) As String
    On Error Resume Next
    SafeExcelText = Application.WorksheetFunction.Text(v, fmt)
    If Err.Number <> 0 Then
        Err.Clear
        SafeExcelText = fallback
    End If
    On Error GoTo 0
End Function

Private Function ExcelSerialToDate(ByVal serial As Double, ByVal date1904 As Boolean) As Date
    If date1904 Then
        ExcelSerialToDate = DateSerial(1904, 1, 1) + serial
    Else
        ExcelSerialToDate = DateSerial(1899, 12, 30) + serial
    End If
End Function

'==========================================================
' DATE NORMALIZATION (locale-safe; avoids CDate)
'==========================================================
Private Function NormalizeDateStringYMD(ByVal s As String, ByVal sheetName As String, ByVal rowIdx As Long, ByVal colIdx As Long) As String

    s = CleanCellString(s)
    If Len(s) = 0 Then
        NormalizeDateStringYMD = ""
        Exit Function
    End If

    ' Strip time if present
    Dim datePart As String
    datePart = Split(s, " ")(0)
    datePart = Replace(datePart, "-", "/")

    Dim parts() As String
    parts = Split(datePart, "/")
    If UBound(parts) <> 2 Then
        Err.Raise vbObjectError + 2200, "GenCSV", _
                  "Unrecognized date '" & s & "' in sheet '" & sheetName & "' at row " & rowIdx & ", col " & colIdx & "."
    End If

    If Not (IsNumeric(parts(0)) And IsNumeric(parts(1)) And IsNumeric(parts(2))) Then
        Err.Raise vbObjectError + 2201, "GenCSV", _
                  "Unrecognized date '" & s & "' in sheet '" & sheetName & "' at row " & rowIdx & ", col " & colIdx & "."
    End If

    Dim yy As Long, mm As Long, dd As Long
    If Len(parts(0)) = 4 Then
        yy = CLng(parts(0)): mm = CLng(parts(1)): dd = CLng(parts(2))
    ElseIf Len(parts(2)) = 4 Then
        mm = CLng(parts(0)): dd = CLng(parts(1)): yy = CLng(parts(2))
    Else
        Err.Raise vbObjectError + 2202, "GenCSV", _
                  "Ambiguous date '" & s & "' in sheet '" & sheetName & "' at row " & rowIdx & ", col " & colIdx & "."
    End If

    Dim dt As Date
    dt = DateSerial(yy, mm, dd)
    If Year(dt) <> yy Or Month(dt) <> mm Or Day(dt) <> dd Then
        Err.Raise vbObjectError + 2203, "GenCSV", _
                  "Invalid date '" & s & "' in sheet '" & sheetName & "' at row " & rowIdx & ", col " & colIdx & "."
    End If

    NormalizeDateStringYMD = Format$(dt, "yyyy/mm/dd")
End Function

'==========================================================
' STRING CLEANING
'   - trims ends
'   - normalizes weird spaces
'   - collapses multiple spaces
'   - SQUASHES all newlines (CR/LF/CRLF removed)
'==========================================================
Private Function CleanCellString(ByVal s As String) As String
    If Len(s) = 0 Then
        CleanCellString = ""
        Exit Function
    End If

    s = Replace(s, ChrW$(160), " ")   ' NBSP
    s = Replace(s, ChrW$(8239), " ")  ' narrow NBSP
    s = Replace(s, ChrW$(65279), "")  ' BOM / zero-width NBSP
    s = Replace(s, ChrW$(8203), "")   ' zero-width space

    s = Replace(s, vbTab, " ")

    ' Squash newlines completely
    s = Replace(s, vbCrLf, "")
    s = Replace(s, vbCr, "")
    s = Replace(s, vbLf, "")

    On Error Resume Next
    s = Application.WorksheetFunction.Trim(s) ' collapses multiple internal spaces
    On Error GoTo 0

    CleanCellString = Trim$(s)
End Function

Private Function CsvEscape(ByVal s As String) As String
    If Len(s) = 0 Then
        CsvEscape = ""
        Exit Function
    End If

    Dim needsQuotes As Boolean
    needsQuotes = (InStr(1, s, ",", vbBinaryCompare) > 0) Or _
                  (InStr(1, s, """", vbBinaryCompare) > 0) Or _
                  (InStr(1, s, vbCr, vbBinaryCompare) > 0) Or _
                  (InStr(1, s, vbLf, vbBinaryCompare) > 0)

    If InStr(1, s, """", vbBinaryCompare) > 0 Then
        s = Replace(s, """", """""")
    End If

    If needsQuotes Then
        CsvEscape = """" & s & """"
    Else
        CsvEscape = s
    End If
End Function

'==========================================================
' RANGE UTILITIES
'==========================================================
Private Function LastColumnInRow(ByVal ws As Worksheet, ByVal rowNum As Long) As Long
    Dim lastCol As Long
    lastCol = ws.Cells(rowNum, ws.Columns.Count).End(xlToLeft).Column
    If lastCol = 1 And Len(CStr(ws.Cells(rowNum, 1).Value2)) = 0 Then lastCol = 0
    LastColumnInRow = lastCol
End Function

Private Function LastDataRowInColumns(ByVal ws As Worksheet, ByVal firstDataRow As Long, ByVal lastCol As Long) As Long
    Dim rngSearch As Range, lastCell As Range
    Set rngSearch = ws.Range(ws.Cells(firstDataRow, 1), ws.Cells(ws.Rows.Count, lastCol))

    Set lastCell = rngSearch.Find(What:="*", LookIn:=xlValues, SearchOrder:=xlByRows, SearchDirection:=xlPrevious)
    If lastCell Is Nothing Then
        LastDataRowInColumns = firstDataRow - 1
    Else
        LastDataRowInColumns = lastCell.Row
    End If
End Function

'==========================================================
' ZIP CREATION (PROD SAFE)
'   - Primary: PowerShell + .NET ZipFile (synchronous)
'   - Fallback: Shell.Application ZIP (best-effort)
'==========================================================
Private Sub CreateZipFromTwoFiles( _
    ByVal zipOut As String, _
    ByVal file1 As String, ByVal entryName1 As String, _
    ByVal file2 As String, ByVal entryName2 As String, _
    ByVal psScriptPath As String)

    Dim errPS As String, errShell As String

    ' Ensure inputs exist
    If Len(Dir$(file1)) = 0 Then Err.Raise vbObjectError + 2401, "GenCSV", "Missing file: " & file1
    If Len(Dir$(file2)) = 0 Then Err.Raise vbObjectError + 2402, "GenCSV", "Missing file: " & file2

    ' Try PowerShell first
    If TryCreateZip_PowerShell(zipOut, file1, entryName1, file2, entryName2, psScriptPath, errPS) Then Exit Sub

    ' Fallback to Shell ZIP if PS is blocked/unavailable
    If TryCreateZip_Shell(zipOut, file1, entryName1, file2, entryName2, errShell) Then Exit Sub

    Err.Raise vbObjectError + 2400, "GenCSV", _
              "Unable to create ZIP." & vbCrLf & vbCrLf & _
              "PowerShell method failed:" & vbCrLf & errPS & vbCrLf & vbCrLf & _
              "Shell method failed:" & vbCrLf & errShell
End Sub

'------------------------
' PowerShell + .NET (preferred)
'------------------------
Private Function TryCreateZip_PowerShell( _
    ByVal zipOut As String, _
    ByVal file1 As String, ByVal entryName1 As String, _
    ByVal file2 As String, ByVal entryName2 As String, _
    ByVal psScriptPath As String, _
    ByRef errMsg As String) As Boolean

    On Error GoTo Fail

    ' Write PS script file
    WriteMakeZipScript psScriptPath

    ' Ensure destination doesn't exist (script also removes, but do it here too)
    On Error Resume Next
    Kill zipOut
    On Error GoTo Fail

    Dim cmd As String
    cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & QuoteArg(psScriptPath) & _
          " -ZipPath " & QuoteArg(zipOut) & _
          " -File1 " & QuoteArg(file1) & " -Name1 " & QuoteArg(entryName1) & _
          " -File2 " & QuoteArg(file2) & " -Name2 " & QuoteArg(entryName2)

    Dim exitCode As Long
    Dim stdout As String, stderr As String
    RunCommandCapture cmd, ZIP_ADD_TIMEOUT_SEC, exitCode, stdout, stderr

    If exitCode <> 0 Then
        errMsg = "ExitCode=" & exitCode & vbCrLf & _
                 "STDOUT:" & vbCrLf & Trim$(stdout) & vbCrLf & _
                 "STDERR:" & vbCrLf & Trim$(stderr)
        TryCreateZip_PowerShell = False
        Exit Function
    End If

    ' Basic sanity check
    If Len(Dir$(zipOut)) = 0 Then
        errMsg = "PowerShell reported success, but ZIP was not created: " & zipOut
        TryCreateZip_PowerShell = False
        Exit Function
    End If

    If GetFileLenSafe(zipOut) <= 0 Then
        errMsg = "PowerShell created ZIP, but it appears empty/invalid: " & zipOut
        TryCreateZip_PowerShell = False
        Exit Function
    End If

    TryCreateZip_PowerShell = True
    Exit Function

Fail:
    errMsg = Err.Number & " - " & Err.Description
    TryCreateZip_PowerShell = False
End Function

Private Sub WriteMakeZipScript(ByVal psScriptPath As String)
    Dim ff As Integer
    ff = FreeFile

    Open psScriptPath For Output As #ff
    Print #ff, "param("
    Print #ff, "  [Parameter(Mandatory=$true)][string]$ZipPath,"
    Print #ff, "  [Parameter(Mandatory=$true)][string]$File1,"
    Print #ff, "  [Parameter(Mandatory=$true)][string]$Name1,"
    Print #ff, "  [Parameter(Mandatory=$true)][string]$File2,"
    Print #ff, "  [Parameter(Mandatory=$true)][string]$Name2"
    Print #ff, ")"
    Print #ff, "$ErrorActionPreference = 'Stop'"
    Print #ff, "Add-Type -AssemblyName System.IO.Compression.FileSystem"
    Print #ff, "if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }"
    Print #ff, "$zip = [System.IO.Compression.ZipFile]::Open($ZipPath, [System.IO.Compression.ZipArchiveMode]::Create)"
    Print #ff, "try {"
    Print #ff, "  [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $File1, $Name1, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null"
    Print #ff, "  [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $File2, $Name2, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null"
    Print #ff, "} finally {"
    Print #ff, "  $zip.Dispose()"
    Print #ff, "}"
    Print #ff, "# Verify entries exist"
    Print #ff, "$zip2 = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)"
    Print #ff, "try {"
    Print #ff, "  $names = $zip2.Entries | ForEach-Object { $_.FullName }"
    Print #ff, "  if ($names -notcontains $Name1) { throw ""Missing entry '$Name1' in zip."" }"
    Print #ff, "  if ($names -notcontains $Name2) { throw ""Missing entry '$Name2' in zip."" }"
    Print #ff, "} finally {"
    Print #ff, "  $zip2.Dispose()"
    Print #ff, "}"
    Print #ff, "Write-Output 'OK'"
    Close #ff
End Sub

Private Sub RunCommandCapture(ByVal cmd As String, ByVal timeoutSeconds As Double, _
                             ByRef exitCode As Long, ByRef stdout As String, ByRef stderr As String)

    Dim wsh As Object, ex As Object
    Set wsh = CreateObject("WScript.Shell")

    On Error GoTo Fail
    Set ex = wsh.Exec(cmd)

    Dim t0 As Double: t0 = Timer
    Do While ex.Status = 0
        DoEvents
        Sleep 50
        If Timer < t0 Then t0 = t0 - 86400#
        If (Timer - t0) > timeoutSeconds Then
            On Error Resume Next
            ex.Terminate
            On Error GoTo 0
            Err.Raise vbObjectError + 2450, "GenCSV", "Timed out waiting for PowerShell ZIP creation."
        End If
    Loop

    stdout = ex.StdOut.ReadAll
    stderr = ex.StdErr.ReadAll
    exitCode = ex.ExitCode
    Exit Sub

Fail:
    Err.Raise vbObjectError + 2451, "GenCSV", "Failed to run command: " & cmd & vbCrLf & Err.Description
End Sub

Private Function QuoteArg(ByVal s As String) As String
    ' Windows file paths cannot contain double-quotes, so simple quoting is safe.
    QuoteArg = """" & s & """"
End Function

'------------------------
' Shell ZIP fallback (best-effort)
'------------------------
Private Function TryCreateZip_Shell( _
    ByVal zipOut As String, _
    ByVal file1 As String, ByVal entryName1 As String, _
    ByVal file2 As String, ByVal entryName2 As String, _
    ByRef errMsg As String) As Boolean

    On Error GoTo Fail

    ' Shell fallback cannot rename entries; it preserves file names.
    ' So require the physical file name to match the desired entry name.
    If StrComp(FileNameFromPath(file1), entryName1, vbTextCompare) <> 0 Then
        Err.Raise vbObjectError + 2460, "GenCSV", "Shell fallback requires file name = entry name for " & file1
    End If
    If StrComp(FileNameFromPath(file2), entryName2, vbTextCompare) <> 0 Then
        Err.Raise vbObjectError + 2461, "GenCSV", "Shell fallback requires file name = entry name for " & file2
    End If

    Dim sourceFolder As String
    sourceFolder = FolderFromPath(file1)
    If Len(sourceFolder) = 0 Then Err.Raise vbObjectError + 2462, "GenCSV", "Invalid source folder for " & file1

    ' Create fresh empty zip
    DeleteFileIfExistsOrRaise zipOut, "Shell fallback cannot overwrite locked ZIP: " & zipOut
    CreateEmptyZipBinary zipOut

    Dim shellApp As Object
    Set shellApp = CreateObject("Shell.Application")

    AddFileToZipAndWait_Shell shellApp, zipOut, sourceFolder, entryName1
    AddFileToZipAndWait_Shell shellApp, zipOut, sourceFolder, entryName2

    If Len(Dir$(zipOut)) = 0 Or GetFileLenSafe(zipOut) <= 0 Then
        Err.Raise vbObjectError + 2463, "GenCSV", "Shell fallback produced no ZIP output."
    End If

    TryCreateZip_Shell = True
    Exit Function

Fail:
    errMsg = Err.Number & " - " & Err.Description
    TryCreateZip_Shell = False
End Function

Private Sub CreateEmptyZipBinary(ByVal zipPath As String)
    ' Truncate first to avoid trailing bytes if file existed
    Dim ff As Integer
    ff = FreeFile
    Open zipPath For Output As #ff
    Close #ff

    Dim b(0 To 21) As Byte
    b(0) = 80  ' P
    b(1) = 75  ' K
    b(2) = 5
    b(3) = 6

    ff = FreeFile
    Open zipPath For Binary Access Write As #ff
    Put #ff, 1, b
    Close #ff
End Sub

Private Sub AddFileToZipAndWait_Shell(ByVal shellApp As Object, ByVal zipPath As String, ByVal sourceFolder As String, ByVal fileName As String)

    Dim vZipPath As Variant: vZipPath = zipPath
    Dim vSourceFolder As Variant: vSourceFolder = sourceFolder

    Dim zipNs As Object
    Set zipNs = GetShellNamespaceWithRetry(shellApp, vZipPath, ZIP_NS_TIMEOUT_SEC)
    If zipNs Is Nothing Then
        Err.Raise vbObjectError + 2470, "GenCSV", "Unable to open ZIP namespace: " & zipPath
    End If

    Dim sourceNs As Object
    Set sourceNs = shellApp.Namespace(vSourceFolder)
    If sourceNs Is Nothing Then
        Err.Raise vbObjectError + 2471, "GenCSV", "Unable to open source folder: " & sourceFolder
    End If

    Dim sourceItem As Object
    Set sourceItem = sourceNs.ParseName(fileName)
    If sourceItem Is Nothing Then
        Err.Raise vbObjectError + 2472, "GenCSV", "Source file not found for zipping: " & fileName
    End If

    Dim startZipLen As Long
    startZipLen = GetFileLenSafe(zipPath)

    Const FOF_SILENT As Long = &H4
    Const FOF_NOCONFIRMATION As Long = &H10
    Const FOF_NOCONFIRMMKDIR As Long = &H200
    Const FOF_NOERRORUI As Long = &H400

    zipNs.CopyHere sourceItem, (FOF_SILENT Or FOF_NOCONFIRMATION Or FOF_NOCONFIRMMKDIR Or FOF_NOERRORUI)

    If Not WaitForZipWriteComplete(zipPath, startZipLen, ZIP_ADD_TIMEOUT_SEC) Then
        Err.Raise vbObjectError + 2473, "GenCSV", "Timed out waiting for ZIP write to complete after adding: " & fileName
    End If

    If Not WaitForFileInZip_Shell(shellApp, zipPath, fileName, ZIP_ADD_TIMEOUT_SEC) Then
        Err.Raise vbObjectError + 2474, "GenCSV", "Timed out waiting for ZIP entry to appear: " & fileName
    End If
End Sub

Private Function GetShellNamespaceWithRetry(ByVal shellApp As Object, ByVal vPath As Variant, ByVal timeoutSec As Double) As Object
    Dim t0 As Double: t0 = Timer

    Do
        On Error Resume Next
        Set GetShellNamespaceWithRetry = shellApp.Namespace(vPath)
        On Error GoTo 0

        If GetShellNamespaceWithRetry Is Nothing Then
            If VarType(vPath) = vbString Then
                On Error Resume Next
                Set GetShellNamespaceWithRetry = shellApp.Namespace(CStr(vPath) & "\")
                On Error GoTo 0
            End If
        End If

        If Not GetShellNamespaceWithRetry Is Nothing Then Exit Function

        Sleep ZIP_POLL_SLEEP_MS
        DoEvents
        If Timer < t0 Then t0 = t0 - 86400#
    Loop While (Timer - t0) < timeoutSec

    Set GetShellNamespaceWithRetry = Nothing
End Function

Private Function WaitForFileInZip_Shell(ByVal shellApp As Object, ByVal zipPath As String, ByVal fileName As String, ByVal timeoutSec As Double) As Boolean
    Dim t0 As Double: t0 = Timer

    Do
        Dim zipNs As Object, itm As Object
        On Error Resume Next
        Set zipNs = shellApp.Namespace(zipPath)
        If zipNs Is Nothing Then Set zipNs = shellApp.Namespace(zipPath & "\")
        On Error GoTo 0

        If Not zipNs Is Nothing Then
            On Error Resume Next
            Set itm = zipNs.ParseName(fileName)
            On Error GoTo 0
            If Not itm Is Nothing Then
                WaitForFileInZip_Shell = True
                Exit Function
            End If
        End If

        Sleep ZIP_POLL_SLEEP_MS
        DoEvents
        If Timer < t0 Then t0 = t0 - 86400#
    Loop While (Timer - t0) < timeoutSec

    WaitForFileInZip_Shell = False
End Function

Private Function WaitForZipWriteComplete(ByVal zipPath As String, ByVal startLen As Long, ByVal timeoutSec As Double) As Boolean
    Dim t0 As Double: t0 = Timer
    Dim lastLen As Long: lastLen = -1
    Dim stableCount As Long: stableCount = 0
    Dim hasGrown As Boolean: hasGrown = False

    Do
        Dim curLen As Long
        curLen = GetFileLenSafe(zipPath)

        If curLen >= 0 Then
            If startLen >= 0 Then
                If curLen > startLen Then hasGrown = True
            Else
                If curLen > 0 Then hasGrown = True
            End If

            If hasGrown Then
                If curLen = lastLen Then
                    stableCount = stableCount + 1
                    If stableCount >= 6 Then
                        WaitForZipWriteComplete = True
                        Exit Function
                    End If
                Else
                    stableCount = 0
                    lastLen = curLen
                End If
            Else
                lastLen = curLen
            End If
        End If

        Sleep 200
        DoEvents
        If Timer < t0 Then t0 = t0 - 86400#
    Loop While (Timer - t0) < timeoutSec

    WaitForZipWriteComplete = False
End Function

Private Function GetFileLenSafe(ByVal path As String) As Long
    On Error Resume Next
    GetFileLenSafe = CLng(FileLen(path))
    If Err.Number <> 0 Then
        Err.Clear
        GetFileLenSafe = -1
    End If
    On Error GoTo 0
End Function

Private Function FileNameFromPath(ByVal fullPath As String) As String
    Dim p As Long
    p = InStrRev(fullPath, Application.PathSeparator)
    If p > 0 Then
        FileNameFromPath = Mid$(fullPath, p + 1)
    Else
        FileNameFromPath = fullPath
    End If
End Function

Private Function FolderFromPath(ByVal fullPath As String) As String
    Dim p As Long
    p = InStrRev(fullPath, Application.PathSeparator)
    If p > 0 Then
        FolderFromPath = Left$(fullPath, p - 1)
    Else
        FolderFromPath = vbNullString
    End If
End Function

'==========================================================
' FILE / TEMP HELPERS
'==========================================================
Private Sub EnsureParentFolderExistsOrRaise(ByVal fullPath As String)
    Dim folderPath As String
    folderPath = FolderFromPath(fullPath)
    If Len(folderPath) = 0 Then
        Err.Raise vbObjectError + 2498, "GenCSV", "Unable to resolve destination folder for: " & fullPath
    End If
    If Len(Dir$(folderPath, vbDirectory)) = 0 Then
        Err.Raise vbObjectError + 2499, "GenCSV", "Destination folder does not exist: " & folderPath
    End If
End Sub

Private Sub EnsureCreatedFileExists(ByVal fullPath As String, ByVal friendlyMessage As String)
    If Len(Dir$(fullPath)) = 0 Then
        Err.Raise vbObjectError + 2501, "GenCSV", friendlyMessage & vbCrLf & fullPath
    End If
End Sub

Private Sub CreateEmptyFile(ByVal path As String)
    Dim ff As Integer: ff = FreeFile
    Open path For Output As #ff
    Close #ff
End Sub

Private Sub DeleteFileIfExistsOrRaise(ByVal path As String, ByVal friendlyMessage As String)
    If Len(Dir$(path)) = 0 Then Exit Sub

    On Error Resume Next
    SetAttr path, vbNormal
    Kill path
    If Err.Number <> 0 Then
        Dim d As String: d = Err.Description
        Err.Clear
        On Error GoTo 0
        Err.Raise vbObjectError + 2500, "GenCSV", friendlyMessage & vbCrLf & path & vbCrLf & d
    End If
    On Error GoTo 0
End Sub

Private Sub CopyFileOverwrite(ByVal src As String, ByVal dest As String)
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    fso.CopyFile src, dest, True
End Sub

Private Function CreateTempFolder(ByVal prefix As String) As String
    EnsureRandomSeeded

    Dim base As String
    base = Environ$("TEMP")
    If Len(base) = 0 Then base = Environ$("TMP")
    If Len(base) = 0 Then base = CurDir$

    If Right$(base, 1) <> Application.PathSeparator Then base = base & Application.PathSeparator

    Dim folderPath As String
    folderPath = base & prefix & Format$(Now, "yyyymmdd_hhnnss") & "_" & CStr(CLng(Rnd() * 100000))

    MkDir folderPath
    CreateTempFolder = folderPath
End Function

Private Sub EnsureRandomSeeded()
    If mRandomSeeded Then Exit Sub
    Randomize
    mRandomSeeded = True
End Sub

Private Function EnsureExtension(ByVal path As String, ByVal ext As String) As String
    If Len(path) = 0 Then
        EnsureExtension = path
    ElseIf LCase$(Right$(path, Len(ext))) <> LCase$(ext) Then
        EnsureExtension = path & ext
    Else
        EnsureExtension = path
    End If
End Function

'==========================================================
' APP STATE / SPEED
'==========================================================
Private Sub SaveAppState(ByRef st As TAppState)
    With Application
        st.ScreenUpdating = .ScreenUpdating
        st.EnableEvents = .EnableEvents
        st.DisplayAlerts = .DisplayAlerts
        st.Calculation = .Calculation
        st.StatusBar = .StatusBar
        st.EnableCancelKey = .EnableCancelKey
    End With
End Sub

Private Sub OptimizeForSpeed(ByVal enable As Boolean, ByRef st As TAppState)
    With Application
        If enable Then
            .ScreenUpdating = False
            .EnableEvents = False
            .DisplayAlerts = False
            .Calculation = xlCalculationManual
            .StatusBar = "Generating CSV + ZIP..."
        Else
            .ScreenUpdating = st.ScreenUpdating
            .EnableEvents = st.EnableEvents
            .DisplayAlerts = st.DisplayAlerts
            .Calculation = st.Calculation
            .StatusBar = st.StatusBar
            .EnableCancelKey = st.EnableCancelKey
        End If
    End With
End Sub
