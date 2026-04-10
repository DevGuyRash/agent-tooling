param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,
    [Parameter(Mandatory = $true)]
    [string]$ReportPath,
    [ValidateSet("full")]
    [string]$ScenarioSet = "full",
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$excel = $null
$workbook = $null
$phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
$phaseDurationsMs = [ordered]@{}
$saved = $false
$scenarioResults = @()

function Complete-Phase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $phaseDurationsMs[$Name] = [int]$phaseTimer.ElapsedMilliseconds
    $phaseTimer.Restart()
}

function Add-ScenarioResult {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [hashtable]$Details
    )

    $entry = [ordered]@{
        name = $Name
        status = $Status
    }
    if ($null -ne $Details) {
        $entry.details = $Details
    }
    $script:scenarioResults += $entry
}

function Remove-AuditArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Worksheet
    )

    foreach ($table in @($Worksheet.ListObjects)) {
        if ([string]$table.Name -like "tbl_excel_sync_*") {
            try { $table.Delete() } catch {}
        }
    }

    try {
        foreach ($query in @($Workbook.Queries)) {
            $queryName = [string]$query.Name
            if ($queryName -like "ExcelSyncAuditQuery*") {
                try { $query.Delete() } catch {}
            }
        }
    } catch {}

    try { $Worksheet.Cells.FormatConditions.Delete() } catch {}
    $Worksheet.Cells.Clear() | Out-Null
}

function New-ConditionalFormattingScenario {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        $Range,
        [Parameter(Mandatory = $true)]
        [string]$Formula,
        [Parameter(Mandatory = $true)]
        [int]$InteriorColor,
        [int]$FontColor = 0,
        [bool]$Bold = $false
    )

    try {
        $rule = $Range.FormatConditions.Add(2, $null, $Formula)
        $rule.Interior.Color = $InteriorColor
        $rule.Font.Color = $FontColor
        $rule.Font.Bold = $Bold
        Add-ScenarioResult -Name $Name -Status "completed" -Details @{
            address = [string]$Range.Address($true, $true, 1)
            formula = $Formula
        }
    } catch {
        Add-ScenarioResult -Name $Name -Status "skipped" -Details @{
            address = [string]$Range.Address($true, $true, 1)
            error = $_.Exception.Message
        }
    }
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
    }
    Remove-AuditArtifacts -Workbook $workbook -Worksheet $auditSheet
    Complete-Phase -Name "prepareAuditSheet"

    $auditSheet.Range("A1:C5").Value2 = @(
        @("Key", "Amount", "Flag"),
        @("A-100", 10, "Y"),
        @("B-200", 20, "N"),
        @("C-300", 30, "Y"),
        @("D-400", 40, "N")
    )
    $primaryTable = $auditSheet.ListObjects.Add(1, $auditSheet.Range("A1:C5"), $null, 1)
    $primaryTable.Name = "tbl_excel_sync_audit"
    $primaryBeforeRange = [string]$primaryTable.Range.Address($false, $false, 1)
    $primaryTable.Range.Cut($auditSheet.Range("F8"))
    $primaryAfterRange = [string]$primaryTable.Range.Address($false, $false, 1)
    Add-ScenarioResult -Name "create-and-move-primary-table" -Status "completed" -Details @{
        table = [string]$primaryTable.Name
        beforeRange = $primaryBeforeRange
        afterRange = $primaryAfterRange
    }

    $auditSheet.Range("H1:J4").Value2 = @(
        @("Category", "Quantity", "Code"),
        @("Office", 2, "OFF"),
        @("Fleet", 5, "FLT"),
        @("Travel", 1, "TRV")
    )
    $secondaryTable = $auditSheet.ListObjects.Add(1, $auditSheet.Range("H1:J4"), $null, 1)
    $secondaryTable.Name = "tbl_excel_sync_secondary"
    Add-ScenarioResult -Name "create-secondary-table" -Status "completed" -Details @{
        table = [string]$secondaryTable.Name
        range = [string]$secondaryTable.Range.Address($false, $false, 1)
    }
    Complete-Phase -Name "createTables"

    New-ConditionalFormattingScenario -Name "cf-single-cell" -Range $auditSheet.Range("N2") -Formula '=LEN($F$9)>0' -InteriorColor 65535 -Bold $true
    New-ConditionalFormattingScenario -Name "cf-rectangular-range" -Range $auditSheet.Range("J2:L6") -Formula '=MOD(ROW()+COLUMN(),2)=0' -InteriorColor 15773696
    New-ConditionalFormattingScenario -Name "cf-column-segment" -Range $auditSheet.Range("M2:M10") -Formula '=ROW()>4' -InteriorColor 13434879
    New-ConditionalFormattingScenario -Name "cf-table-body" -Range $primaryTable.DataBodyRange -Formula '=LEN($F9)>0' -InteriorColor 10092543 -Bold $true

    $primaryKeyColumn = $null
    try { $primaryKeyColumn = $primaryTable.ListColumns.Item(1).DataBodyRange } catch {}
    if ($null -ne $primaryKeyColumn) {
        New-ConditionalFormattingScenario -Name "cf-table-column" -Range $primaryKeyColumn -Formula '=LEFT($F9,1)="A"' -InteriorColor 5296274 -FontColor 16777215
    } else {
        Add-ScenarioResult -Name "cf-table-column" -Status "skipped" -Details @{ reason = "primary-table-first-column-missing" }
    }
    Complete-Phase -Name "applyConditionalFormatting"

    $createdQueries = @()
    foreach ($querySpec in @(
        @{
            Name = "ExcelSyncAuditQuery_Main"
            Formula = "let Source = #table({""Key"",""Amount""}, {{""A-100"", 10}, {""B-200"", 20}, {""C-300"", 30}}) in Source"
        },
        @{
            Name = "ExcelSyncAuditQuery_Defaults"
            Formula = "let Source = #table({""Category"",""Quantity""}, {{""Office"", 2}, {""Fleet"", 5}, {""Travel"", 1}}) in Source"
        }
    )) {
        try {
            [void]$workbook.Queries.Add($querySpec.Name, $querySpec.Formula)
            $createdQueries += $querySpec.Name
            Add-ScenarioResult -Name ("query-" + $querySpec.Name) -Status "completed" -Details @{
                query = $querySpec.Name
            }
        } catch {
            Add-ScenarioResult -Name ("query-" + $querySpec.Name) -Status "skipped" -Details @{
                query = $querySpec.Name
                error = $_.Exception.Message
            }
        }
    }
    Complete-Phase -Name "addPowerQueries"

    $workbook.Save() | Out-Null
    $saved = $true
    Complete-Phase -Name "saveWorkbook"

    $report = @{
        ran = $true
        workbook = $WorkbookPath
        scenarioSet = $ScenarioSet
        createdSheet = "ExcelSync_Audit"
        createdTables = @(
            @{
                name = "tbl_excel_sync_audit"
                beforeRange = $primaryBeforeRange
                afterRange = $primaryAfterRange
            },
            @{
                name = "tbl_excel_sync_secondary"
                range = [string]$secondaryTable.Range.Address($false, $false, 1)
            }
        )
        createdQueries = $createdQueries
        conditionalFormattingCount = [int]$auditSheet.Cells.FormatConditions.Count
        scenarios = $scenarioResults
        phaseDurationsMs = $phaseDurationsMs
    }

    $reportJson = $report | ConvertTo-Json -Depth 8
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
