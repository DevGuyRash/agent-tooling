param(
    [string]$WorkbookPath = "C:\Users\E135328\repos\carvana-workflows\excel\tr_upload_sheet\tr_upload_template.xlsm",
    [int]$Rows = 1000,
    [int]$Iterations = 5,
    [double]$TimeoutSeconds = 30,
    [string]$SheetName = "AP_INVOICE_LINES_INTERFACE",
    [string]$TableName = "tbl_invoice_lines"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-PasteData {
    param([int]$RowCount)

    $data = New-Object 'object[,]' $RowCount, 7

    for ($i = 0; $i -lt $RowCount; $i++) {
        $lineNumber = ($i % 3) + 1
        $stockNumber = 2004500000 + $i
        $pidValue = 700 + ($i % 200)

        $data[$i, 0] = $lineNumber
        $data[$i, 1] = $null
        $data[$i, 2] = [double]($lineNumber * 125.5)
        $data[$i, 3] = $null
        $data[$i, 4] = $null
        $data[$i, 5] = $null
        $data[$i, 6] = "STOCK NUMBER $stockNumber PID NUMBER $pidValue BRAKE JOB"
    }

    return $data
}

function Wait-ForCondition {
    param(
        [scriptblock]$Condition,
        [System.Diagnostics.Stopwatch]$Stopwatch,
        [double]$TimeoutSeconds
    )

    while (-not (& $Condition)) {
        if ($Stopwatch.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
            return $false
        }

        Start-Sleep -Milliseconds 15
    }

    return $true
}

function Test-ManagedFormulasReady {
    param(
        $Excel,
        $ListObject,
        [int]$StartRowIndex,
        [int]$EndRowIndex
    )

    if ($ListObject.ListRows.Count -lt $EndRowIndex) {
        return $false
    }

    foreach ($header in @("*Invoice ID", "Project Number", "Attribute 6")) {
        $listColumn = $ListObject.ListColumns.Item($header)
        $startCell = $listColumn.DataBodyRange.Cells.Item($StartRowIndex, 1)
        $endCell = $listColumn.DataBodyRange.Cells.Item($EndRowIndex, 1)

        if (-not [bool]$startCell.HasFormula) {
            return $false
        }

        if (-not [bool]$endCell.HasFormula) {
            return $false
        }
    }

    return ($Excel.CalculationState -eq 0)
}

function Get-ExpectedInvoiceCount {
    param($Data)

    $rowCount = $Data.GetLength(0)
    $count = 0

    for ($i = 0; $i -lt $rowCount; $i++) {
        if ([string]$Data[$i, 0] -eq "1") {
            $count++
        }
    }

    return $count
}

function Test-InvoiceSyncReady {
    param(
        $Excel,
        $InvoiceTable,
        [int]$ExpectedRows
    )

    if ([int]$InvoiceTable.ListRows.Count -lt $ExpectedRows) {
        return $false
    }

    $invoiceIdRange = $InvoiceTable.ListColumns.Item("*Invoice ID").DataBodyRange
    if ($invoiceIdRange -eq $null) {
        return $false
    }

    if (-not [bool]$invoiceIdRange.Cells.Item($ExpectedRows, 1).HasFormula) {
        return $false
    }

    return ($Excel.CalculationState -eq 0)
}

function Invoke-WorkbookMacro {
    param(
        $Excel,
        $Workbook,
        [string]$MacroName
    )

    $Excel.Run(("'{0}'!{1}" -f $Workbook.Name, $MacroName), $true) | Out-Null
}

function Get-RangeAddress {
    param(
        [int]$TopRow,
        [int]$BottomRow
    )

    return "B{0}:H{1}" -f $TopRow, $BottomRow
}

if (-not (Test-Path -LiteralPath $WorkbookPath)) {
    throw "Workbook not found: $WorkbookPath"
}

$excel = $null
$results = @()
$payload = New-PasteData -RowCount $Rows
$expectedInvoiceAdds = Get-ExpectedInvoiceCount -Data $payload

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false

    for ($iteration = 1; $iteration -le $Iterations; $iteration++) {
        $tempPath = Join-Path $env:TEMP ("tr_upload_sheet_bench_{0}_{1}.xlsm" -f $PID, $iteration)
        Copy-Item -LiteralPath $WorkbookPath -Destination $tempPath -Force

        $workbook = $null
        try {
            $workbook = $excel.Workbooks.Open($tempPath)
            $worksheet = $workbook.Worksheets.Item($SheetName)
            $worksheet.Activate() | Out-Null

            $listObject = $worksheet.ListObjects.Item($TableName)
            $invoiceSheet = $workbook.Worksheets.Item("AP_INVOICES_INTERFACE")
            $invoiceTable = $invoiceSheet.ListObjects.Item("tbl_invoices")
            $initialRows = [int]$listObject.ListRows.Count
            $initialInvoiceRows = [int]$invoiceTable.ListRows.Count
            $pasteTopRow = [int]($listObject.Range.Row + $listObject.Range.Rows.Count)
            $pasteBottomRow = $pasteTopRow + $Rows - 1

            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            $targetRange = $worksheet.Range((Get-RangeAddress -TopRow $pasteTopRow -BottomRow $pasteBottomRow))
            $targetRange.Value2 = $payload
            $pasteReturnMs = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)

            $expanded = Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -Condition {
                return ([int]$listObject.ListRows.Count -ge ($initialRows + $Rows))
            }

            if (-not $expanded) {
                throw "Timed out waiting for native table expansion."
            }

            $startRowIndex = [int]($pasteTopRow - $listObject.DataBodyRange.Row + 1)
            $endRowIndex = $startRowIndex + $Rows - 1

            $lineReady = Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -Condition {
                Test-ManagedFormulasReady -Excel $excel -ListObject $listObject -StartRowIndex $startRowIndex -EndRowIndex $endRowIndex
            }

            if (-not $lineReady) {
                throw "Timed out waiting for managed formulas to appear."
            }

            $lineReadyMs = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)
            $expectedInvoiceRows = $initialInvoiceRows + $expectedInvoiceAdds

            $deferredReady = Wait-ForCondition -Stopwatch $stopwatch -TimeoutSeconds $TimeoutSeconds -Condition {
                Test-InvoiceSyncReady -Excel $excel -InvoiceTable $invoiceTable -ExpectedRows $expectedInvoiceRows
            }

            if (-not $deferredReady) {
                throw "Timed out waiting for deferred invoice sync to complete."
            }

            $deferredFlushMs = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)

            $flushWatch = [System.Diagnostics.Stopwatch]::StartNew()
            Invoke-WorkbookMacro -Excel $excel -Workbook $workbook -MacroName "AP_BeforeExportFlush"
            $exportFlushMs = [math]::Round($flushWatch.Elapsed.TotalMilliseconds, 2)

            $results += [pscustomobject]@{
                Iteration = $iteration
                PasteReturnMs = $pasteReturnMs
                LineReadyMs = $lineReadyMs
                DeferredFlushMs = $deferredFlushMs
                ExportFlushMs = $exportFlushMs
                Workbook = $tempPath
            }
        }
        finally {
            if ($workbook -ne $null) {
                $workbook.Close($false)
            }

            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
    }
}
finally {
    if ($excel -ne $null) {
        $excel.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    }

    [gc]::Collect()
    [gc]::WaitForPendingFinalizers()
}

$sortedPaste = $results | Sort-Object PasteReturnMs
$sortedLineReady = $results | Sort-Object LineReadyMs
$sortedDeferred = $results | Sort-Object DeferredFlushMs
$sortedExportFlush = $results | Sort-Object ExportFlushMs
$medianIndex = [int][math]::Floor(($results.Count - 1) / 2)

$summary = [pscustomobject]@{
    Workbook = $WorkbookPath
    Rows = $Rows
    Iterations = $Iterations
    MedianPasteReturnMs = $sortedPaste[$medianIndex].PasteReturnMs
    MaxPasteReturnMs = ($sortedPaste | Measure-Object -Property PasteReturnMs -Maximum).Maximum
    MedianLineReadyMs = $sortedLineReady[$medianIndex].LineReadyMs
    MaxLineReadyMs = ($sortedLineReady | Measure-Object -Property LineReadyMs -Maximum).Maximum
    MedianDeferredFlushMs = $sortedDeferred[$medianIndex].DeferredFlushMs
    MaxDeferredFlushMs = ($sortedDeferred | Measure-Object -Property DeferredFlushMs -Maximum).Maximum
    MedianExportFlushMs = $sortedExportFlush[$medianIndex].ExportFlushMs
    MaxExportFlushMs = ($sortedExportFlush | Measure-Object -Property ExportFlushMs -Maximum).Maximum
}

$results | Format-Table -AutoSize
""
$summary | Format-List
