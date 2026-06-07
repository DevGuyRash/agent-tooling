param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,
    [int]$TimeoutSeconds = 30,
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Wait-ForCondition {
    param(
        [scriptblock]$Condition,
        [System.Diagnostics.Stopwatch]$Stopwatch,
        [int]$TimeoutSeconds,
        [string]$FailureMessage
    )

    while (-not (& $Condition)) {
        if ($Stopwatch.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
            throw $FailureMessage
        }

        Start-Sleep -Milliseconds 50
    }
}

function Get-RangeAddress {
    param(
        [int]$TopRow,
        [int]$BottomRow
    )

    "B{0}:H{1}" -f $TopRow, $BottomRow
}

function Get-BorderSignature {
    param($Cell)

    $edges = @(7, 8, 9, 10)
    $parts = foreach ($edge in $edges) {
        $border = $Cell.Borders.Item($edge)
        "{0}:{1}:{2}:{3}" -f $edge, [int]$border.LineStyle, [int]$border.Weight, [int]$border.Color
    }

    return ($parts -join "|")
}

if (-not (Test-Path -LiteralPath $WorkbookPath)) {
    throw "Workbook not found: $WorkbookPath"
}

$linePayload = New-Object "object[,]" 3, 7
$linePayload[0, 0] = 1
$linePayload[0, 2] = 10
$linePayload[0, 6] = "FORMAT TEST FIRST"
$linePayload[1, 0] = 1
$linePayload[1, 2] = 20
$linePayload[1, 6] = "FORMAT TEST SECOND"
$linePayload[2, 0] = 1
$linePayload[2, 2] = 30
$linePayload[2, 6] = "FORMAT TEST THIRD"

$excel = $null
$workbook = $null
$tempPath = $null

try {
    $tempPath = Join-Path $env:TEMP ("generic_workflow_record_number_format_{0}.xlsm" -f $PID)
    Copy-Item -LiteralPath $WorkbookPath -Destination $tempPath -Force

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = [bool]$Visible
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false

    $workbook = $excel.Workbooks.Open($tempPath)
    $linesSheet = $workbook.Worksheets.Item("DATA_RECORD_LINES")
    $recordSheet = $workbook.Worksheets.Item("DATA_RECORDS")

    $linesSheet.Activate() | Out-Null

    $linesTable = $linesSheet.ListObjects.Item("tbl_record_lines")
    $recordTable = $recordSheet.ListObjects.Item("tbl_records")
    $initialRecordRows = [int]$recordTable.ListRows.Count

    $pasteTopRow = [int]($linesTable.Range.Row + $linesTable.Range.Rows.Count)
    $pasteBottomRow = $pasteTopRow + 2
    $targetRange = $linesSheet.Range((Get-RangeAddress -TopRow $pasteTopRow -BottomRow $pasteBottomRow))

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $targetRange.Value2 = $linePayload

    $expectedRecordRows = $initialRecordRows + 3
    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for record rows to append during live sync." -Condition {
        return ([int]$recordTable.ListRows.Count -ge $expectedRecordRows)
    }

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for record number formulas on appended rows." -Condition {
        $recordNumberRange = $recordTable.ListColumns.Item("*Record Number").DataBodyRange
        return [bool]$recordNumberRange.Cells.Item($expectedRecordRows, 1).HasFormula
    }

    $expectedCell = $recordTable.ListColumns.Item("*Record Number").DataBodyRange.Cells.Item($initialRecordRows, 1)
    $expectedBorders = Get-BorderSignature -Cell $expectedCell
    $newCell = $recordTable.ListColumns.Item("*Record Number").DataBodyRange.Cells.Item($initialRecordRows + 1, 1)
    $actualBorders = Get-BorderSignature -Cell $newCell

    if ($actualBorders -ne $expectedBorders) {
        throw "Expected appended record-number cell borders '$expectedBorders' but found '$actualBorders'."
    }

    Write-Output "Record-number format propagation regression check passed."
}
finally {
    if ($workbook -ne $null) {
        $workbook.Close($false)
    }

    if ($excel -ne $null) {
        $excel.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    }

    if ($tempPath -and (Test-Path -LiteralPath $tempPath)) {
        Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
    }

    [gc]::Collect()
    [gc]::WaitForPendingFinalizers()
}
