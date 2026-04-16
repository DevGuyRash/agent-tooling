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
        [object[]]$InvoiceInputs,
        [int]$StartRow = 1
    )

    $supplierRange = $InvoiceTable.ListColumns.Item("**Supplier Number").DataBodyRange
    $dateRange = $InvoiceTable.ListColumns.Item("*Invoice Date").DataBodyRange

    for ($i = 0; $i -lt $InvoiceInputs.Count; $i++) {
        $targetRow = $StartRow + $i
        $supplierRange.Cells.Item($targetRow, 1).Value2 = $InvoiceInputs[$i].SupplierNumber
        $dateRange.Cells.Item($targetRow, 1).Value2 = $InvoiceInputs[$i].InvoiceDate
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
$linePayload[5, 6] = "STOCK NUMBER 2004500001 BRAKE JOB"

$linePayload[6, 0] = 1
$linePayload[6, 1] = $null
$linePayload[6, 2] = 60
$linePayload[6, 3] = $null
$linePayload[6, 4] = $null
$linePayload[6, 5] = $null
$linePayload[6, 6] = "NO STOCK HERE"

$linePayload[7, 0] = 1
$linePayload[7, 1] = $null
$linePayload[7, 2] = 70
$linePayload[7, 3] = $null
$linePayload[7, 4] = $null
$linePayload[7, 5] = $null
$linePayload[7, 6] = "ALT SUPPLIER NO STOCK"

$linePayload[8, 0] = 1
$linePayload[8, 1] = $null
$linePayload[8, 2] = 80
$linePayload[8, 3] = $null
$linePayload[8, 4] = $null
$linePayload[8, 5] = $null
$linePayload[8, 6] = "ALT DATE NO STOCK"

$invoiceInputs = @(
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-200"; InvoiceDate = [datetime]"2026-03-10" }
    [pscustomobject]@{ SupplierNumber = "SUP-100"; InvoiceDate = [datetime]"2026-03-11" }
)

$expectedInvoiceNumbers = @(
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
    $tempPath = Join-Path $env:TEMP ("tr_upload_invoice_number_test_{0}.xlsm" -f $PID)
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
    $initialInvoiceRows = [int]$invoicesTable.ListRows.Count

    $pasteTopRow = [int]($linesTable.Range.Row + $linesTable.Range.Rows.Count)
    $pasteBottomRow = $pasteTopRow + 8
    $targetRange = $linesSheet.Range((Get-RangeAddress -TopRow $pasteTopRow -BottomRow $pasteBottomRow))

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $targetRange.Value2 = $linePayload

    Invoke-WorkbookMacro -Excel $excel -Workbook $workbook -MacroName "AP_BeforeExportFlush"

    $appendedStartRow = $initialInvoiceRows + 1
    $expectedInvoiceRows = $initialInvoiceRows + $invoiceInputs.Count

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for invoice rows to sync from invoice lines." -Condition {
        return ([int]$invoicesTable.ListRows.Count -ge $expectedInvoiceRows)
    }

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for invoice ID formulas to populate." -Condition {
        $invoiceIdRange = $invoicesTable.ListColumns.Item("*Invoice ID").DataBodyRange
        return [bool]$invoiceIdRange.Cells.Item($expectedInvoiceRows, 1).HasFormula
    }

    Set-InvoiceInputValues -InvoiceTable $invoicesTable -InvoiceInputs $invoiceInputs -StartRow $appendedStartRow
    Invoke-WorkbookMacro -Excel $excel -Workbook $workbook -MacroName "AP_BeforeExportFlush"
    $excel.CalculateFullRebuild()

    Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -FailureMessage "Timed out waiting for invoice numbers to stabilize." -Condition {
        try {
            Assert-InvoiceNumbers -InvoiceTable $invoicesTable -ExpectedNumbers $expectedInvoiceNumbers
            return $true
        }
        catch {
            return $false
        }
    }

    Assert-InvoiceNumbers -InvoiceTable $invoicesTable -ExpectedNumbers $expectedInvoiceNumbers

    Write-Output "Invoice number sequencing regression check passed."
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
