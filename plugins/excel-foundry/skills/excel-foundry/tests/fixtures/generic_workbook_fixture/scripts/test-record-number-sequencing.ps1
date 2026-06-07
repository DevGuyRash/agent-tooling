param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,
    [int]$TimeoutSeconds = 20,
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

function Set-RecordInputValues {
    param(
        $RecordTable,
        [object[]]$RecordInputs,
        [int]$StartRow = 1
    )

    $supplierRange = $RecordTable.ListColumns.Item("**Supplier Number").DataBodyRange
    $dateRange = $RecordTable.ListColumns.Item("*Record Date").DataBodyRange

    for ($i = 0; $i -lt $RecordInputs.Count; $i++) {
        $targetRow = $StartRow + $i
        $supplierRange.Cells.Item($targetRow, 1).Value2 = $RecordInputs[$i].SupplierNumber
        $dateRange.Cells.Item($targetRow, 1).Value2 = $RecordInputs[$i].RecordDate
    }
}

function Assert-RecordNumbers {
    param(
        $RecordTable,
        [string[]]$ExpectedNumbers
    )

    $recordNumberRange = $RecordTable.ListColumns.Item("*Record Number").DataBodyRange
    $startIndex = ([int]$recordNumberRange.Rows.Count) - $ExpectedNumbers.Count + 1

    if ($startIndex -lt 1) {
        throw ("Record table has {0} rows but expected at least {1}." -f [int]$recordNumberRange.Rows.Count, $ExpectedNumbers.Count)
    }

    for ($i = 0; $i -lt $ExpectedNumbers.Count; $i++) {
        $actual = [string]$recordNumberRange.Cells.Item($startIndex + $i, 1).Text
        $expected = $ExpectedNumbers[$i]

        if ($actual -ne $expected) {
            throw ("Record row {0} expected '{1}' but found '{2}'." -f ($startIndex + $i), $expected, $actual)
        }
    }
}

function Invoke-WorkbookMacro {
    param(
        $Excel,
        $Workbook,
        [string]$MacroName
    )

    $Excel.Run(("'{0}'!{1}" -f $Workbook.Name, $MacroName), $true) | Out-Null
}

if (-not (Test-Path -LiteralPath $WorkbookPath)) {
    throw "Workbook not found: $WorkbookPath"
}

$linePayload = New-Object "object[,]" 9, 7
$linePayload[0, 0] = 1
$linePayload[0, 1] = $null
$linePayload[0, 2] = 10
$linePayload[0, 3] = $null
$linePayload[0, 4] = $null
$linePayload[0, 5] = $null
$linePayload[0, 6] = "LABOR ONLY"

$linePayload[1, 0] = 1
$linePayload[1, 1] = $null
$linePayload[1, 2] = 20
$linePayload[1, 3] = $null
$linePayload[1, 4] = $null
$linePayload[1, 5] = $null
$linePayload[1, 6] = "ADMIN FEE"

$linePayload[2, 0] = 1
$linePayload[2, 1] = $null
$linePayload[2, 2] = 30
$linePayload[2, 3] = $null
$linePayload[2, 4] = $null
$linePayload[2, 5] = $null
$linePayload[2, 6] = "MULTI LINE HEADER"

$linePayload[3, 0] = 2
$linePayload[3, 1] = $null
$linePayload[3, 2] = 5
$linePayload[3, 3] = $null
$linePayload[3, 4] = $null
$linePayload[3, 5] = $null
$linePayload[3, 6] = "MULTI LINE DETAIL"

$linePayload[4, 0] = 1
$linePayload[4, 1] = $null
$linePayload[4, 2] = 40
$linePayload[4, 3] = $null
$linePayload[4, 4] = $null
$linePayload[4, 5] = $null
$linePayload[4, 6] = "DOC FEE"

$linePayload[5, 0] = 1
$linePayload[5, 1] = $null
$linePayload[5, 2] = 50
$linePayload[5, 3] = $null
$linePayload[5, 4] = $null
$linePayload[5, 5] = $null
$linePayload[5, 6] = "ASSET NUMBER 2004500001 BRAKE JOB"

$linePayload[6, 0] = 1
$linePayload[6, 1] = $null
$linePayload[6, 2] = 60
$linePayload[6, 3] = $null
$linePayload[6, 4] = $null
$linePayload[6, 5] = $null
$linePayload[6, 6] = "NO ASSET HERE"

$linePayload[7, 0] = 1
$linePayload[7, 1] = $null
$linePayload[7, 2] = 70
$linePayload[7, 3] = $null
$linePayload[7, 4] = $null
$linePayload[7, 5] = $null
$linePayload[7, 6] = "ALT SUPPLIER NO ASSET"

$linePayload[8, 0] = 1
$linePayload[8, 1] = $null
$linePayload[8, 2] = 80
$linePayload[8, 3] = $null
$linePayload[8, 4] = $null
$linePayload[8, 5] = $null
$linePayload[8, 6] = "ALT DATE NO ASSET"

$recordInputs = @(
    [pscustomobject]@{ SupplierNumber = "SUP-100"; RecordDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; RecordDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; RecordDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; RecordDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; RecordDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; RecordDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-200"; RecordDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; RecordDate = [datetime]"2026-03-11" }
)

$expectedRecordNumbers = @(
    "03102026-TR",
    "03102026-1-TR",
    "03102026-2-TR",
    "03102026-3-TR",
    "2004500001-TR",
    "03102026-4-TR",
    "03102026-TR",
    "03112026-TR"
)

$excel = $null
$workbook = $null
$tempPath = $null

try {
    $tempPath = Join-Path $env:TEMP ("generic_workflow_record_number_test_{0}.xlsm" -f $PID)
    Copy-Item -LiteralPath $WorkbookPath -Destination $tempPath -Force

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = [bool]$Visible
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false

    $workbook = $excel.Workbooks.Open($tempPath)
    $linesSheet = $workbook.Worksheets.Item("DATA_RECORD_LINES")
    $recordsSheet = $workbook.Worksheets.Item("DATA_RECORDS")

    $linesSheet.Activate() | Out-Null

    $linesTable = $linesSheet.ListObjects.Item("tbl_record_lines")
    $recordsTable = $recordsSheet.ListObjects.Item("tbl_records")
    $initialRecordRows = [int]$recordsTable.ListRows.Count

    $pasteTopRow = [int]($linesTable.Range.Row + $linesTable.Range.Rows.Count)
    $pasteBottomRow = $pasteTopRow + 8
    $targetRange = $linesSheet.Range((Get-RangeAddress -TopRow $pasteTopRow -BottomRow $pasteBottomRow))

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $targetRange.Value2 = $linePayload

    Invoke-WorkbookMacro -Excel $excel -Workbook $workbook -MacroName "AP_BeforeExportFlush"

    $appendedStartRow = $initialRecordRows + 1
    $expectedRecordRows = $initialRecordRows + $recordInputs.Count

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for record rows to sync from record lines." -Condition {
        return ([int]$recordsTable.ListRows.Count -ge $expectedRecordRows)
    }

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for record ID formulas to populate." -Condition {
        $recordIdRange = $recordsTable.ListColumns.Item("*Record ID").DataBodyRange
        return [bool]$recordIdRange.Cells.Item($expectedRecordRows, 1).HasFormula
    }

    Set-RecordInputValues -RecordTable $recordsTable -RecordInputs $recordInputs -StartRow $appendedStartRow
    Invoke-WorkbookMacro -Excel $excel -Workbook $workbook -MacroName "AP_BeforeExportFlush"
    $excel.CalculateFullRebuild()

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for record numbers to stabilize." -Condition {
        try {
            Assert-RecordNumbers -RecordTable $recordsTable -ExpectedNumbers $expectedRecordNumbers
            return $true
        }
        catch {
            return $false
        }
    }

    Assert-RecordNumbers -RecordTable $recordsTable -ExpectedNumbers $expectedRecordNumbers

    Write-Output "Record number sequencing regression check passed."
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
