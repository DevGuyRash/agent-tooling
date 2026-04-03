param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $WorkbookPath)) {
    throw "Workbook not found: $WorkbookPath"
}

$excel = $null
$workbook = $null
$tempPath = $null
$singleZipPath = $null
$multiZipPath = $null

try {
    $tempPath = Join-Path $env:TEMP ("tr_upload_export_import_set_{0}.xlsm" -f $PID)
    Copy-Item -LiteralPath $WorkbookPath -Destination $tempPath -Force

    $singleZipPath = Join-Path $env:TEMP ("tr_upload_export_single_{0}.zip" -f $PID)
    $multiZipPath = Join-Path $env:TEMP ("tr_upload_export_multi_{0}.zip" -f $PID)
    Remove-Item -LiteralPath $singleZipPath, $multiZipPath -Force -ErrorAction SilentlyContinue

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = [bool]$Visible
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false

    $workbook = $excel.Workbooks.Open($tempPath)
    $invoiceSheet = $workbook.Worksheets.Item("AP_INVOICES_INTERFACE")
    $invoiceTable = $invoiceSheet.ListObjects.Item("tbl_invoices")
    $importSetRange = $invoiceTable.ListColumns.Item("Import Set").DataBodyRange

    $excel.Run(("'{0}'!AP_BeforeExportFlush" -f $workbook.Name), $true) | Out-Null
    $excel.CalculateFullRebuild()

    $expectedSingle = [string]$importSetRange.Cells.Item(1, 1).Text
    if ([string]::IsNullOrWhiteSpace($expectedSingle)) {
        throw "Expected a nonblank Import Set in the first invoice row."
    }

    Set-Clipboard -Value ""
    $excel.Run(("'{0}'!GenCSV_ToPath" -f $workbook.Name), $singleZipPath, $false) | Out-Null

    if (-not (Test-Path -LiteralPath $singleZipPath)) {
        throw "Single-import-set export did not create the target ZIP."
    }

    $actualSingleClipboard = [string](Get-Clipboard -Raw)
    if ($actualSingleClipboard -ne $expectedSingle) {
        throw ("Expected clipboard value '{0}' after single-import-set export but found '{1}'." -f $expectedSingle, $actualSingleClipboard)
    }

    $importSetRange.Cells.Item(2, 1).Formula = "=""MULTI-SECOND-IMPORT-SET"""
    Set-Clipboard -Value "UNCHANGED"
    $excel.Run(("'{0}'!GenCSV_ToPath" -f $workbook.Name), $multiZipPath, $false) | Out-Null

    if (-not (Test-Path -LiteralPath $multiZipPath)) {
        throw "Multiple-import-set export did not create the target ZIP."
    }

    $actualMultiClipboard = [string](Get-Clipboard -Raw)
    if ($actualMultiClipboard -ne "UNCHANGED") {
        throw ("Expected clipboard to remain unchanged for multiple import sets, but found '{0}'." -f $actualMultiClipboard)
    }

    Write-Output "Export ZIP path + import-set clipboard regression checks passed."
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

    if ($singleZipPath -and (Test-Path -LiteralPath $singleZipPath)) {
        Remove-Item -LiteralPath $singleZipPath -Force -ErrorAction SilentlyContinue
    }

    if ($multiZipPath -and (Test-Path -LiteralPath $multiZipPath)) {
        Remove-Item -LiteralPath $multiZipPath -Force -ErrorAction SilentlyContinue
    }

    [gc]::Collect()
    [gc]::WaitForPendingFinalizers()
}
