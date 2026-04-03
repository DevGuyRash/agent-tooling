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

function Set-InvoiceInputValues {
    param(
        $InvoiceTable,
        [object[]]$InvoiceInputs
    )

    $supplierRange = $InvoiceTable.ListColumns.Item("**Supplier Number").DataBodyRange
    $dateRange = $InvoiceTable.ListColumns.Item("*Invoice Date").DataBodyRange

    for ($i = 0; $i -lt $InvoiceInputs.Count; $i++) {
        $supplierRange.Cells.Item($i + 1, 1).Value2 = $InvoiceInputs[$i].SupplierNumber
        $dateRange.Cells.Item($i + 1, 1).Value2 = $InvoiceInputs[$i].InvoiceDate
    }
}

function Assert-InvoiceNumbers {
    param(
        $InvoiceTable,
        [string[]]$ExpectedNumbers
    )

    $invoiceNumberRange = $InvoiceTable.ListColumns.Item("*Invoice Number").DataBodyRange
    $startIndex = ([int]$invoiceNumberRange.Rows.Count) - $ExpectedNumbers.Count + 1

    if ($startIndex -lt 1) {
        throw ("Invoice table has {0} rows but expected at least {1}." -f [int]$invoiceNumberRange.Rows.Count, $ExpectedNumbers.Count)
    }

    for ($i = 0; $i -lt $ExpectedNumbers.Count; $i++) {
        $actual = [string]$invoiceNumberRange.Cells.Item($startIndex + $i, 1).Text
        $expected = $ExpectedNumbers[$i]

        if ($actual -ne $expected) {
            throw ("Invoice row {0} expected '{1}' but found '{2}'." -f ($startIndex + $i), $expected, $actual)
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

$linePayload = New-Object "object[,]" 4, 7
$linePayload[0, 0] = 1
$linePayload[0, 1] = $null
$linePayload[0, 2] = 10
$linePayload[0, 3] = $null
$linePayload[0, 4] = $null
$linePayload[0, 5] = $null
$linePayload[0, 6] = "OKC2-2004267606-1-JF2GTAEC2LH246053-58586367"

$linePayload[1, 0] = 1
$linePayload[1, 1] = $null
$linePayload[1, 2] = 20
$linePayload[1, 3] = $null
$linePayload[1, 4] = $null
$linePayload[1, 5] = $null
$linePayload[1, 6] = "OKC2-2004267606-ADJ-JF2GTAEC2LH246053-58586367"

$linePayload[2, 0] = 1
$linePayload[2, 1] = $null
$linePayload[2, 2] = 30
$linePayload[2, 3] = $null
$linePayload[2, 4] = $null
$linePayload[2, 5] = $null
$linePayload[2, 6] = "2004401729-OKC2-2004401729-ADJ-KNDJ23AU9S7936386-59922767"

$linePayload[3, 0] = 1
$linePayload[3, 1] = $null
$linePayload[3, 2] = 40
$linePayload[3, 3] = $null
$linePayload[3, 4] = $null
$linePayload[3, 5] = $null
$linePayload[3, 6] = "STOCK NUMBER 2004500001 BRAKE JOB"

$invoiceInputs = @(
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
)

$expectedInvoiceNumbers = @(
    "2004267606-1-TR"
    "2004267606-ADJ-TR"
    "2004401729-ADJ-TR"
    "2004500001-TR"
)

$excel = $null
$workbook = $null
$tempPath = $null

try {
    $tempPath = Join-Path $env:TEMP ("tr_upload_invoice_number_stock_vin_patterns_{0}.xlsm" -f $PID)
    Copy-Item -LiteralPath $WorkbookPath -Destination $tempPath -Force

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = [bool]$Visible
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false

    $workbook = $excel.Workbooks.Open($tempPath)
    $linesSheet = $workbook.Worksheets.Item("AP_INVOICE_LINES_INTERFACE")
    $invoicesSheet = $workbook.Worksheets.Item("AP_INVOICES_INTERFACE")

    $linesSheet.Activate() | Out-Null

    $linesTable = $linesSheet.ListObjects.Item("tbl_invoice_lines")
    $invoicesTable = $invoicesSheet.ListObjects.Item("tbl_invoices")

    $pasteTopRow = [int]($linesTable.Range.Row + $linesTable.Range.Rows.Count)
    $pasteBottomRow = $pasteTopRow + ($invoiceInputs.Count - 1)
    $targetRange = $linesSheet.Range((Get-RangeAddress -TopRow $pasteTopRow -BottomRow $pasteBottomRow))

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $targetRange.Value2 = $linePayload

    Invoke-WorkbookMacro -Excel $excel -Workbook $workbook -MacroName "AP_BeforeExportFlush"

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for invoice rows to sync from invoice lines." -Condition {
        return ([int]$invoicesTable.ListRows.Count -ge $invoiceInputs.Count)
    }

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for invoice ID formulas to populate." -Condition {
        $invoiceIdRange = $invoicesTable.ListColumns.Item("*Invoice ID").DataBodyRange
        return [bool]$invoiceIdRange.Cells.Item($invoiceInputs.Count, 1).HasFormula
    }

    Set-InvoiceInputValues -InvoiceTable $invoicesTable -InvoiceInputs $invoiceInputs
    Invoke-WorkbookMacro -Excel $excel -Workbook $workbook -MacroName "AP_BeforeExportFlush"
    $excel.CalculateFullRebuild()

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for VIN-style stock invoice numbers to stabilize." -Condition {
        try {
            Assert-InvoiceNumbers -InvoiceTable $invoicesTable -ExpectedNumbers $expectedInvoiceNumbers
            return $true
        }
        catch {
            return $false
        }
    }

    Assert-InvoiceNumbers -InvoiceTable $invoicesTable -ExpectedNumbers $expectedInvoiceNumbers

    Write-Output "VIN-style stock invoice-number regression check passed."
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
