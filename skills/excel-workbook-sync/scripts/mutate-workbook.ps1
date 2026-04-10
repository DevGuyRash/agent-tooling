param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,
    [Parameter(Mandatory = $true)]
    [string]$ReportPath,
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$excel = $null
$workbook = $null
$phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
$phaseDurationsMs = [ordered]@{}
$saved = $false

function Complete-Phase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $phaseDurationsMs[$Name] = [int]$phaseTimer.ElapsedMilliseconds
    $phaseTimer.Restart()
}

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = [bool]$Visible
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false
    try {
        $excel.Calculation = -4135 # xlCalculationManual
    } catch {}
    try {
        $excel.AutomationSecurity = 3 # msoAutomationSecurityForceDisable
    } catch {}

    $workbook = $excel.Workbooks.Open($WorkbookPath)
    Complete-Phase -Name "openWorkbook"

    try {
        $excel.Calculation = -4135 # xlCalculationManual
    } catch {}

    $auditSheet = $null
    foreach ($candidate in @($workbook.Worksheets)) {
        if ([string]$candidate.Name -eq "ExcelSync_Audit") {
            $auditSheet = $candidate
            break
        }
    }
    if ($null -eq $auditSheet) {
        $auditSheet = $workbook.Worksheets.Add()
        $auditSheet.Name = "ExcelSync_Audit"
    } else {
        $auditSheet.Cells.Clear() | Out-Null
    }
    Complete-Phase -Name "prepareAuditSheet"

    $auditSheet.Range("A1:C4").Value2 = @(
        @("Key", "Amount", "Flag"),
        @("A-100", 10, "Y"),
        @("B-200", 20, "N"),
        @("C-300", 30, "Y")
    )
    $tableRange = $auditSheet.Range("A1:C4")
    $table = $auditSheet.ListObjects.Add(1, $tableRange, $null, 1)
    $table.Name = "tbl_excel_sync_audit"

    $beforeRange = [string]$table.Range.Address($false, $false, 1)
    $table.Range.Cut($auditSheet.Range("F8"))
    $afterRange = [string]$table.Range.Address($false, $false, 1)
    Complete-Phase -Name "createAndMoveTable"

    $cellRule = $auditSheet.Range("J2:J6").FormatConditions.Add(2, $null, '=MOD(ROW(),2)=0')
    $cellRule.Interior.Color = 65535
    $cellRule.Font.Bold = $true

    $tableRule = $table.DataBodyRange.FormatConditions.Add(2, $null, '=LEN($F8)>0')
    $tableRule.Interior.Color = 15773696
    $tableRule.Font.Bold = $true
    Complete-Phase -Name "applyConditionalFormatting"

    $queryAdded = $false
    try {
        [void]$workbook.Queries.Add(
            "ExcelSyncAuditQuery",
            "let Source = #table({""Key"",""Amount""}, {{""A-100"", 10}, {""B-200"", 20}}) in Source"
        )
        $queryAdded = $true
    } catch {}
    Complete-Phase -Name "addPowerQuery"

    $workbook.Save() | Out-Null
    $saved = $true
    Complete-Phase -Name "saveWorkbook"

    $report = @{
        ran = $true
        workbook = $WorkbookPath
        createdSheet = "ExcelSync_Audit"
        createdTable = "tbl_excel_sync_audit"
        beforeRange = $beforeRange
        afterRange = $afterRange
        queryAdded = $queryAdded
        conditionalFormattingCount = [int]$auditSheet.Cells.FormatConditions.Count
        phaseDurationsMs = $phaseDurationsMs
    }

    $reportJson = $report | ConvertTo-Json -Depth 5
    $reportDir = Split-Path -Parent $ReportPath
    if (-not (Test-Path -LiteralPath $reportDir)) {
        New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    }
    Set-Content -LiteralPath $ReportPath -Value $reportJson -Encoding UTF8
    $reportJson
}
finally {
    if ($workbook -ne $null) {
        $workbook.Close(-not $saved)
    }
    if ($excel -ne $null) {
        $excel.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    }
    [gc]::Collect()
    [gc]::WaitForPendingFinalizers()
}
