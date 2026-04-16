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
    $tempPath = Join-Path $env:TEMP ("tr_upload_invoice_number_format_{0}.xlsm" -f $PID)
    Copy-Item -LiteralPath $WorkbookPath -Destination $tempPath -Force

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = [bool]$Visible
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false

    $workbook = $excel.Workbooks.Open($tempPath)
    $linesSheet = $workbook.Worksheets.Item("AP_INVOICE_LINES_INTERFACE")
    $invoiceSheet = $workbook.Worksheets.Item("AP_INVOICES_INTERFACE")

    $linesSheet.Activate() | Out-Null

    $linesTable = $linesSheet.ListObjects.Item("tbl_invoice_lines")
    $invoiceTable = $invoiceSheet.ListObjects.Item("tbl_invoices")
    $initialInvoiceRows = [int]$invoiceTable.ListRows.Count

    $pasteTopRow = [int]($linesTable.Range.Row + $linesTable.Range.Rows.Count)
    $pasteBottomRow = $pasteTopRow + 2
    $targetRange = $linesSheet.Range((Get-RangeAddress -TopRow $pasteTopRow -BottomRow $pasteBottomRow))

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $targetRange.Value2 = $linePayload

    $expectedInvoiceRows = $initialInvoiceRows + 3
    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for invoice rows to append during live sync." -Condition {
        return ([int]$invoiceTable.ListRows.Count -ge $expectedInvoiceRows)
    }

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for invoice number formulas on appended rows." -Condition {
        $invoiceNumberRange = $invoiceTable.ListColumns.Item("*Invoice Number").DataBodyRange
        return [bool]$invoiceNumberRange.Cells.Item($expectedInvoiceRows, 1).HasFormula
    }

    $expectedCell = $invoiceTable.ListColumns.Item("*Invoice Number").DataBodyRange.Cells.Item($initialInvoiceRows, 1)
    $expectedBorders = Get-BorderSignature -Cell $expectedCell
    $newCell = $invoiceTable.ListColumns.Item("*Invoice Number").DataBodyRange.Cells.Item($initialInvoiceRows + 1, 1)
    $actualBorders = Get-BorderSignature -Cell $newCell

    if ($actualBorders -ne $expectedBorders) {
        throw "Expected appended invoice-number cell borders '$expectedBorders' but found '$actualBorders'."
    }

    Write-Output "Invoice-number format propagation regression check passed."
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
