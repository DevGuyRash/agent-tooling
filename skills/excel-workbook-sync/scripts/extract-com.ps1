param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,
    [string]$OutputRoot,
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'ExcelSync.Common.ps1')

$context = $null

function Convert-RangeValueToRows {
    param($Range)

    if ($null -eq $Range) {
        return @()
    }

    $value = $Range.Value2
    if ($null -eq $value) {
        return @()
    }

    if ($value -isnot [System.Array]) {
        return @(@($value))
    }

    if ($value.Rank -eq 1) {
        $row = @()
        foreach ($item in $value) {
            $row += $item
        }
        return @($row)
    }

    $rows = @()
    for ($row = $value.GetLowerBound(0); $row -le $value.GetUpperBound(0); $row++) {
        $current = @()
        for ($col = $value.GetLowerBound(1); $col -le $value.GetUpperBound(1); $col++) {
            $current += $value[$row, $col]
        }
        $rows += ,$current
    }
    return $rows
}

function Export-CodeComponent {
    param(
        $Workbook,
        $Component,
        [string]$OutputRoot
    )

    if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
        return $null
    }

    $code = ""
    try {
        $lineCount = $Component.CodeModule.CountOfLines
        if ($lineCount -gt 0) {
            $code = $Component.CodeModule.Lines(1, $lineCount)
        }
    } catch {
        $code = ""
    }

    $type = [int]$Component.Type
    $relativePath = $null
    if ($type -eq 100) {
        if ($Component.Name -eq "ThisWorkbook") {
            $relativePath = "macros/workbook/ThisWorkbook.vba"
        } else {
            $worksheet = $null
            foreach ($sheet in @($Workbook.Worksheets)) {
                if ($sheet.CodeName -eq $Component.Name) {
                    $worksheet = $sheet
                    break
                }
            }
            $sheetName = if ($worksheet -ne $null) { [string]$worksheet.Name } else { [string]$Component.Name }
            $relativePath = "macros/sheets/{0}.vba" -f $sheetName
        }
    } else {
        $relativePath = "macros/modules/{0}.vba" -f $Component.Name
    }

    $targetPath = Join-Path $OutputRoot $relativePath
    $targetDir = Split-Path -Parent $targetPath
    if (-not (Test-Path -LiteralPath $targetDir)) {
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    }
    Set-Content -LiteralPath $targetPath -Value $code -Encoding UTF8
    return $relativePath.Replace("\", "/")
}

$excel = $null
$workbook = $null
$phaseTimer = [System.Diagnostics.Stopwatch]::StartNew()
$phaseDurationsMs = [ordered]@{}

function Complete-Phase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $phaseDurationsMs[$Name] = [int]$phaseTimer.ElapsedMilliseconds
    $phaseTimer.Restart()
}

try {
    $context = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible
    $excel = $context.Excel
    $workbook = $context.Workbook
    Complete-Phase -Name "openWorkbook"
    try {
        $excel.Calculation = -4135 # xlCalculationManual
    } catch {}

    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
        if (-not (Test-Path -LiteralPath $OutputRoot)) {
            New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
        }
    }

    $sheets = @()
    $tables = @()
    $tableMappings = @()
    $conditionalFormatting = @()
    foreach ($worksheet in @($workbook.Worksheets)) {
        $sheetTables = @()
        foreach ($table in @($worksheet.ListObjects)) {
            $headers = @()
            foreach ($column in @($table.ListColumns)) {
                $headers += [string]$column.Name
            }

            $rows = Convert-RangeValueToRows -Range $table.DataBodyRange
            $tableRange = $table.Range.Address($false, $false, 1)
            $topLeft = $table.HeaderRowRange.Cells.Item(1, 1).Address($false, $false, 1)
            $tableInfo = @{
                sheet = [string]$worksheet.Name
                name = [string]$table.Name
                topLeft = $topLeft
                range = $tableRange
                headers = $headers
                rows = $rows
            }
            $tables += $tableInfo
            $sheetTables += @{ name = [string]$table.Name; range = $tableRange }

            $mappingHeaders = @()
            for ($i = 1; $i -le $table.ListColumns.Count; $i++) {
                $column = $table.ListColumns.Item($i)
                $headerCell = $column.Range.Cells.Item(1, 1).Address($false, $false, 1)
                $dataRange = if ($null -ne $column.DataBodyRange) { $column.DataBodyRange.Address($false, $false, 1) } else { $null }
                $mappingHeaders += @{
                    header = [string]$column.Name
                    column = [string]$column.Range.Columns.Item(1).Address($false, $false, 1).Split(":")[0] -replace '\d+', ''
                    headerCell = $headerCell
                    dataRange = $dataRange
                }
            }
            $tableMappings += @{
                sheet = [string]$worksheet.Name
                table = [string]$table.Name
                range = $tableRange
                headers = $mappingHeaders
            }
        }

        foreach ($rule in @($worksheet.Cells.FormatConditions)) {
            $format = @{
                interiorColor = $null
                fontColor = $null
                bold = $false
            }
            $formula = ""
            $type = ""
            try {
                if ($rule.Interior.Color -ne $null) {
                    $format.interiorColor = ('#{0:X6}' -f ([int]$rule.Interior.Color -band 0xFFFFFF))
                }
            } catch {}
            try {
                if ($rule.Font.Color -ne $null) {
                    $format.fontColor = ('#{0:X6}' -f ([int]$rule.Font.Color -band 0xFFFFFF))
                }
                $format.bold = [bool]$rule.Font.Bold
            } catch {}
            try { $formula = [string]$rule.Formula1 } catch { $formula = "" }
            try { $type = [string]$rule.Type } catch { $type = "" }

            $conditionalFormatting += @{
                id = "{0}:{1}:{2}" -f $worksheet.Name, $rule.AppliesTo.Address($true, $true, 1), [int]$rule.Priority
                sheet = [string]$worksheet.Name
                address = [string]$rule.AppliesTo.Address($true, $true, 1)
                type = $type
                formula = $formula
                priority = [int]$rule.Priority
                stopIfTrue = [bool]$rule.StopIfTrue
                format = $format
            }
        }

        $sheets += @{
            name = [string]$worksheet.Name
            sheetId = $null
            path = $null
            tables = $sheetTables
            conditionalFormattingRuleCount = @($conditionalFormatting | Where-Object { $_.sheet -eq [string]$worksheet.Name }).Count
        }
    }
    Complete-Phase -Name "extractSheetsTablesAndFormatting"

    $names = @()
    foreach ($name in @($workbook.Names)) {
        $names += @{
            name = [string]$name.Name
            localSheetId = $null
            hidden = -not [bool]$name.Visible
            refersTo = [string]$name.RefersTo
        }
    }
    Complete-Phase -Name "extractNames"

    $connections = @()
    foreach ($connection in @($workbook.Connections)) {
        $connString = ""
        $command = ""
        try {
            $connString = [string]$connection.OLEDBConnection.Connection
            $command = [string]$connection.OLEDBConnection.CommandText
        } catch {}
        $connections += @{
            name = [string]$connection.Name
            description = [string]$connection.Description
            type = [string]$connection.Type
            background = $false
            connection = $connString
            command = $command
        }
    }
    Complete-Phase -Name "extractConnections"

    $queries = @()
    try {
        foreach ($query in @($workbook.Queries)) {
            $queries += @{
                name = [string]$query.Name
                description = [string]$query.Description
                formula = [string]$query.Formula
                source = "com"
            }
        }
    } catch {}
    Complete-Phase -Name "extractQueries"

    $vba = @{
        present = $false
        sha256 = $null
        size = 0
        accessible = $false
        components = @()
        references = @()
    }

    try {
        $project = $workbook.VBProject
        $vba.accessible = $true
        $vba.present = $true
        foreach ($component in @($project.VBComponents)) {
            $artifactPath = Export-CodeComponent -Workbook $workbook -Component $component -OutputRoot $OutputRoot
            $lineCount = 0
            try { $lineCount = [int]$component.CodeModule.CountOfLines } catch {}
            $vba.components += @{
                name = [string]$component.Name
                type = [int]$component.Type
                lineCount = $lineCount
                artifactPath = $artifactPath
            }
        }
        foreach ($reference in @($project.References)) {
            $vba.references += @{
                name = [string]$reference.Name
                fullPath = [string]$reference.FullPath
                guid = [string]$reference.GUID
                major = [int]$reference.Major
                minor = [int]$reference.Minor
                builtIn = [bool]$reference.BuiltIn
            }
        }
    } catch {}
    Complete-Phase -Name "extractVba"

    $result = @{
        engine = "com"
        generatedAt = [DateTimeOffset]::UtcNow.ToString("o")
        workbook = @{
            path = $WorkbookPath
            name = [System.IO.Path]::GetFileName($WorkbookPath)
            format = [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant()
            sha256 = $null
        }
        sheets = $sheets
        tables = $tables
        tableMappings = $tableMappings
        names = $names
        conditionalFormatting = $conditionalFormatting
        connections = $connections
        queries = $queries
        powerQuery = @{
            dataMashupPresent = ($queries.Count -gt 0)
            dataMashupSha256 = $null
            packageEntries = @()
        }
        vba = $vba
        diagnostics = @{
            phaseDurationsMs = $phaseDurationsMs
        }
    }

    $result | ConvertTo-Json -Depth 10
}
finally {
    if ($null -ne $context) {
        Close-ExcelWorkbook -Context $context -SaveChanges:$false
    }
}
