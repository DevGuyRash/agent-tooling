param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [ValidateSet("push", "pull")]
    [string]$Direction = "push",
    [string]$WorkbookPath,
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "ExcelFoundry.Common.ps1")

function Get-RangeFromAddress {
    param(
        [Parameter(Mandatory = $true)]
        $Worksheet,
        [Parameter(Mandatory = $true)]
        [string]$Address
    )

    return $Worksheet.Range($Address)
}

function Set-RangeValues {
    param(
        [Parameter(Mandatory = $true)]
        $Range,
        [Parameter(Mandatory = $true)]
        [object[]]$Values
    )

    $rowCount = $Values.Count
    $colCount = $Values[0].Count
    $target = $Range.Resize($rowCount, $colCount)
    $matrix = New-Object 'object[,]' $rowCount, $colCount
    for ($r = 0; $r -lt $rowCount; $r++) {
        for ($c = 0; $c -lt $colCount; $c++) {
            $matrix[$r, $c] = $Values[$r][$c]
        }
    }
    $target.Value2 = $matrix

    return $target
}

function Ensure-TableDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $TableSpec
    )

    try {
        [void](Ensure-DirectTableDefinition -Workbook $Workbook -TableSpec $TableSpec -Mode 'set')
    }
    catch {
        throw "Failed to sync table '$($TableSpec.name)' on sheet '$($TableSpec.sheet)' at '$($TableSpec.topLeft)': $($_.Exception.Message)"
    }
}

function Export-TableDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $TableSpec
    )

    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName ([string]$TableSpec.sheet)
    $listObject = Get-ListObjectByName -Worksheet $worksheet -TableName ([string]$TableSpec.name)

    $headers = @()
    $headerCount = [int]$listObject.HeaderRowRange.Columns.Count
    for ($col = 1; $col -le $headerCount; $col++) {
        $headers += [string]$listObject.HeaderRowRange.Cells.Item(1, $col).Value2
    }

    $rows = @()
    if ($null -ne $listObject.DataBodyRange) {
        $rowCount = [int]$listObject.DataBodyRange.Rows.Count
        $colCount = [int]$listObject.DataBodyRange.Columns.Count

        for ($r = 1; $r -le $rowCount; $r++) {
            $rowValues = @()
            for ($c = 1; $c -le $colCount; $c++) {
                $rowValues += $listObject.DataBodyRange.Cells.Item($r, $c).Value2
            }
            $rows += ,$rowValues
        }
    }

    return [pscustomobject]@{
        sheet = [string]$TableSpec.sheet
        name = [string]$TableSpec.name
        topLeft = [string]$TableSpec.topLeft
        headers = $headers
        rows = $rows
    }
}

function Test-WorksheetIncluded {
    param(
        [Parameter(Mandatory = $true)]
        $Worksheet,
        $DiscoverySpec
    )

    if ($null -eq $DiscoverySpec) {
        return $true
    }

    $sheetFilters = @()
    if ($null -ne $DiscoverySpec.PSObject.Properties["sheets"]) {
        $sheetFilters = @($DiscoverySpec.sheets)
    }
    if ($sheetFilters.Count -eq 0) {
        return $true
    }

    foreach ($sheetName in $sheetFilters) {
        if ([string]$Worksheet.Name -eq [string]$sheetName) {
            return $true
        }
    }

    return $false
}

function Export-DiscoveredTableDefinitions {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        $DiscoverySpec
    )

    $definitions = @()
    foreach ($worksheet in $Workbook.Worksheets) {
        if (-not (Test-WorksheetIncluded -Worksheet $worksheet -DiscoverySpec $DiscoverySpec)) {
            continue
        }

        foreach ($listObject in $worksheet.ListObjects) {
            $headers = @()
            $headerCount = [int]$listObject.HeaderRowRange.Columns.Count
            for ($col = 1; $col -le $headerCount; $col++) {
                $headers += [string]$listObject.HeaderRowRange.Cells.Item(1, $col).Value2
            }

            $rows = @()
            if ($null -ne $listObject.DataBodyRange) {
                $rowCount = [int]$listObject.DataBodyRange.Rows.Count
                $colCount = [int]$listObject.DataBodyRange.Columns.Count

                for ($r = 1; $r -le $rowCount; $r++) {
                    $rowValues = @()
                    for ($c = 1; $c -le $colCount; $c++) {
                        $rowValues += $listObject.DataBodyRange.Cells.Item($r, $c).Value2
                    }
                    $rows += ,$rowValues
                }
            }

            $definitions += [pscustomobject]@{
                sheet = [string]$worksheet.Name
                name = [string]$listObject.Name
                topLeft = [string]$listObject.Range.Cells.Item(1, 1).Address($false, $false)
                headers = $headers
                rows = $rows
            }
        }
    }

    return $definitions
}

function Ensure-WorkbookName {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $NameSpec
    )

    $nameValue = [string]$NameSpec.name
    $refersTo = [string]$NameSpec.refersTo

    try {
        $existingName = $Workbook.Names.Item($nameValue)
        $existingName.RefersTo = $refersTo
    }
    catch {
        $Workbook.Names.Add($nameValue, $refersTo) | Out-Null
    }
}

function Export-WorkbookName {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $NameSpec
    )

    $existingName = $Workbook.Names.Item([string]$NameSpec.name)
    return [pscustomobject]@{
        name = [string]$NameSpec.name
        refersTo = [string]$existingName.RefersTo
    }
}

function Test-NameIncluded {
    param(
        [Parameter(Mandatory = $true)]
        $NameObject,
        $DiscoverySpec
    )

    $nameText = [string]$NameObject.Name
    $excludeBuiltIn = $true
    if ($null -ne $DiscoverySpec -and $null -ne $DiscoverySpec.PSObject.Properties["excludeBuiltIn"]) {
        $excludeBuiltIn = [bool]$DiscoverySpec.excludeBuiltIn
    }

    if ($excludeBuiltIn -and $nameText.StartsWith("_xlnm.", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }
    if ($excludeBuiltIn -and $nameText.StartsWith("_xlfn.", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }
    if ($excludeBuiltIn -and $nameText.StartsWith("_xlpm.", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }
    if ($excludeBuiltIn -and $nameText.EndsWith("!_FilterDatabase", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }

    return $true
}

function Export-DiscoveredWorkbookNames {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        $DiscoverySpec
    )

    $definitions = @()
    foreach ($existingName in $Workbook.Names) {
        if (-not (Test-NameIncluded -NameObject $existingName -DiscoverySpec $DiscoverySpec)) {
            continue
        }

        $definitions += [pscustomobject]@{
            name = [string]$existingName.Name
            refersTo = [string]$existingName.RefersTo
        }
    }

    return @($definitions | Sort-Object name)
}

function Resolve-CfTargetRange {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $RuleSpec
    )

    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName ([string]$RuleSpec.sheet)

    if ($null -ne $RuleSpec.PSObject.Properties["address"] -and $null -ne $RuleSpec.address) {
        return ,$worksheet.Range([string]$RuleSpec.address)
    }

    $listObject = Get-ListObjectByName -Worksheet $worksheet -TableName ([string]$RuleSpec.table)
    if ($null -ne $RuleSpec.PSObject.Properties["column"] -and $null -ne $RuleSpec.column) {
        return ,$listObject.ListColumns.Item([string]$RuleSpec.column).DataBodyRange
    }

    return ,$listObject.DataBodyRange
}

function Remove-ManagedFormatConditions {
    param(
        [Parameter(Mandatory = $true)]
        $TargetRange,
        [Parameter(Mandatory = $true)]
        [string]$ReplaceIfFormulaContains
    )

    $count = 0
    try {
        $count = [int]$TargetRange.FormatConditions.Count
    }
    catch {
        return
    }

    for ($index = $count; $index -ge 1; $index--) {
        try {
            $formatCondition = $TargetRange.FormatConditions.Item($index)
        }
        catch {
            continue
        }
        $formula1 = ""
        try {
            $formula1 = [string]$formatCondition.Formula1
        }
        catch {
        }

        if ($formula1 -like "*$ReplaceIfFormulaContains*") {
            $formatCondition.Delete()
        }
    }
}

function Apply-FormatConditionStyle {
    param(
        [Parameter(Mandatory = $true)]
        $FormatCondition,
        $FormatSpec
    )

    if ($null -eq $FormatSpec) {
        return
    }

    if ($null -ne $FormatSpec.interiorColor) {
        $FormatCondition.Interior.Color = Convert-ColorHexToBgrInt -HexColor ([string]$FormatSpec.interiorColor)
    }
    if ($null -ne $FormatSpec.fontColor) {
        $FormatCondition.Font.Color = Convert-ColorHexToBgrInt -HexColor ([string]$FormatSpec.fontColor)
    }
    if ($null -ne $FormatSpec.bold) {
        $FormatCondition.Font.Bold = [bool]$FormatSpec.bold
    }
}

function Remove-SupportedFormatConditions {
    param(
        [Parameter(Mandatory = $true)]
        $TargetRange
    )

    $count = 0
    try {
        $count = [int]$TargetRange.FormatConditions.Count
    }
    catch {
        return
    }

    for ($index = $count; $index -ge 1; $index--) {
        try {
            $formatCondition = $TargetRange.FormatConditions.Item($index)
            $typeName = Get-CfTypeName -FormatCondition $formatCondition
            if (Test-CfSupported -TypeName $typeName) {
                $formatCondition.Delete()
            }
        }
        catch {
        }
    }
}

function Set-ConditionPriorityAndStop {
    param(
        [Parameter(Mandatory = $true)]
        $FormatCondition,
        [Parameter(Mandatory = $true)]
        $RuleSpec
    )

    if ($null -ne $RuleSpec.PSObject.Properties["stopIfTrue"] -and $null -ne $RuleSpec.stopIfTrue) {
        try {
            $FormatCondition.StopIfTrue = [bool]$RuleSpec.stopIfTrue
        }
        catch {
        }
    }
    if ($null -ne $RuleSpec.PSObject.Properties["priority"] -and $null -ne $RuleSpec.priority) {
        try {
            $FormatCondition.Priority = [int]$RuleSpec.priority
        }
        catch {
        }
    }
}

function New-ConditionalFormatRule {
    param(
        [Parameter(Mandatory = $true)]
        $TargetRange,
        [Parameter(Mandatory = $true)]
        $RuleSpec,
        [Parameter(Mandatory = $true)]
        $Workbook
    )

    $typeName =
        if ($null -ne $RuleSpec.PSObject.Properties["type"] -and -not [string]::IsNullOrWhiteSpace([string]$RuleSpec.type)) {
            [string]$RuleSpec.type
        }
        else {
            "expression"
        }

    switch ($typeName) {
        "expression" {
            return $TargetRange.FormatConditions.Add(2, 0, [string]$RuleSpec.formula)
        }
        "cell-value" {
            $formula1 = [string]$RuleSpec.formula
            $formula2 = $null
            if ($null -ne $RuleSpec.PSObject.Properties["formula2"]) {
                $formula2 = [string]$RuleSpec.formula2
            }
            $operator = 0
            if ($null -ne $RuleSpec.PSObject.Properties["operator"] -and $null -ne $RuleSpec.operator) {
                $operator = [int]$RuleSpec.operator
            }
            return $TargetRange.FormatConditions.Add(1, $operator, $formula1, $formula2)
        }
        "unique-values" {
            $condition = $TargetRange.FormatConditions.AddUniqueValues()
            if ($null -ne $RuleSpec.PSObject.Properties["dupeUnique"] -and $null -ne $RuleSpec.dupeUnique) {
                try {
                    $condition.DupeUnique = [int]$RuleSpec.dupeUnique
                }
                catch {
                }
            }
            return $condition
        }
        "top10" {
            $condition = $TargetRange.FormatConditions.AddTop10()
            if ($null -ne $RuleSpec.PSObject.Properties["rank"] -and $null -ne $RuleSpec.rank) {
                try { $condition.Rank = [int]$RuleSpec.rank } catch {}
            }
            if ($null -ne $RuleSpec.PSObject.Properties["percent"] -and $null -ne $RuleSpec.percent) {
                try { $condition.Percent = [bool]$RuleSpec.percent } catch {}
            }
            if ($null -ne $RuleSpec.PSObject.Properties["topBottom"] -and $null -ne $RuleSpec.topBottom) {
                try { $condition.TopBottom = [int]$RuleSpec.topBottom } catch {}
            }
            return $condition
        }
        "above-average" {
            $condition = $TargetRange.FormatConditions.AddAboveAverage()
            if ($null -ne $RuleSpec.PSObject.Properties["aboveBelow"] -and $null -ne $RuleSpec.aboveBelow) {
                try { $condition.AboveBelow = [int]$RuleSpec.aboveBelow } catch {}
            }
            if ($null -ne $RuleSpec.PSObject.Properties["numStdDev"] -and $null -ne $RuleSpec.numStdDev) {
                try { $condition.NumStdDev = [int]$RuleSpec.numStdDev } catch {}
            }
            return $condition
        }
        "color-scale" {
            $criteriaSpec = @($RuleSpec.criteria)
            $colorScaleType = if ($criteriaSpec.Count -ge 3) { 3 } else { 2 }
            $condition = $TargetRange.FormatConditions.AddColorScale($colorScaleType)
            for ($index = 0; $index -lt $criteriaSpec.Count; $index++) {
                $criterion = $condition.ColorScaleCriteria.Item($index + 1)
                $criterionSpec = $criteriaSpec[$index]
                try {
                    $criterion.Type = [int]$criterionSpec.type
                }
                catch {
                }
                if ($null -ne $criterionSpec.PSObject.Properties["value"] -and $null -ne $criterionSpec.value) {
                    try {
                        $criterion.Value = $criterionSpec.value
                    }
                    catch {
                    }
                }
                if ($null -ne $criterionSpec.PSObject.Properties["formatColor"] -and $null -ne $criterionSpec.formatColor) {
                    $criterion.FormatColor.Color = Convert-ColorHexToBgrInt -HexColor ([string]$criterionSpec.formatColor)
                }
            }
            return $condition
        }
        "data-bar" {
            $condition = $TargetRange.FormatConditions.AddDatabar()
            if ($null -ne $RuleSpec.PSObject.Properties["barColor"] -and $null -ne $RuleSpec.barColor) {
                try {
                    $condition.BarColor.Color = Convert-ColorHexToBgrInt -HexColor ([string]$RuleSpec.barColor)
                }
                catch {
                }
            }
            return $condition
        }
        "icon-set" {
            $condition = $TargetRange.FormatConditions.AddIconSetCondition()
            if ($null -ne $RuleSpec.PSObject.Properties["iconSetId"] -and $null -ne $RuleSpec.iconSetId) {
                try {
                    $condition.IconSet = $Workbook.Application.IconSets.Item([int]$RuleSpec.iconSetId)
                }
                catch {
                }
            }
            if ($null -ne $RuleSpec.PSObject.Properties["reverseOrder"] -and $null -ne $RuleSpec.reverseOrder) {
                try { $condition.ReverseOrder = [bool]$RuleSpec.reverseOrder } catch {}
            }
            if ($null -ne $RuleSpec.PSObject.Properties["showIconOnly"] -and $null -ne $RuleSpec.showIconOnly) {
                try { $condition.ShowIconOnly = [bool]$RuleSpec.showIconOnly } catch {}
            }
            return $condition
        }
        default {
            throw "Unsupported conditional formatting type for push: $typeName"
        }
    }
}

function Ensure-ConditionalFormatRule {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $RuleSpec,
        [switch]$ClearExisting
    )

    $targetRange = Resolve-CfTargetRange -Workbook $Workbook -RuleSpec $RuleSpec
    if ($ClearExisting) {
        Remove-SupportedFormatConditions -TargetRange $targetRange
    }
    elseif ($null -ne $RuleSpec.PSObject.Properties["replaceIfFormulaContains"] -and $null -ne $RuleSpec.replaceIfFormulaContains) {
        Remove-ManagedFormatConditions -TargetRange $targetRange -ReplaceIfFormulaContains ([string]$RuleSpec.replaceIfFormulaContains)
    }

    $formatCondition = New-ConditionalFormatRule -TargetRange $targetRange -RuleSpec $RuleSpec -Workbook $Workbook
    Set-ConditionPriorityAndStop -FormatCondition $formatCondition -RuleSpec $RuleSpec
    Apply-FormatConditionStyle -FormatCondition $formatCondition -FormatSpec $RuleSpec.format
}

function Export-ConditionalFormatRule {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $RuleSpec
    )

    $allRules = @(Get-ConditionalFormattingQuery -Workbook $Workbook | Where-Object {
        $_.sheet -eq [string]$RuleSpec.sheet -and
        $_.address -eq [string]$RuleSpec.address
    } | Sort-Object priority, id)

    $match = Resolve-ConditionalFormatRuleMatch -RuleSpec $RuleSpec -Candidates $allRules

    $match.id = [string]$RuleSpec.id
    return $match
}

function Test-CfTypeSupported {
    param($FormatCondition)

    try {
        $typeName = Get-CfTypeName -FormatCondition $FormatCondition
        return (Test-CfSupported -TypeName $typeName)
    }
    catch {
        return $false
    }
}

function Export-DiscoveredConditionalFormatRules {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        $DiscoverySpec
    )

    $definitions = @()
    $query = @(Get-ConditionalFormattingQuery -Workbook $Workbook)

    foreach ($worksheet in $Workbook.Worksheets) {
        if (-not (Test-WorksheetIncluded -Worksheet $worksheet -DiscoverySpec $DiscoverySpec)) {
            continue
        }

        $usedRange = $worksheet.UsedRange
        if ($null -eq $usedRange) {
            continue
        }

        $formatConditions = $usedRange.FormatConditions
        $count = 0
        try {
            $count = [int]$formatConditions.Count
        }
        catch {
            continue
        }

        for ($index = 1; $index -le $count; $index++) {
            $candidate = $formatConditions.Item($index)
            if (-not (Test-CfTypeSupported -FormatCondition $candidate)) {
                continue
            }

            $appliesTo = $null
            try {
                $appliesTo = $candidate.AppliesTo
            }
            catch {
                continue
            }

            $exported = @($query | Where-Object {
                $_.sheet -eq [string]$worksheet.Name -and
                $_.address -eq [string]$appliesTo.Address() -and
                $_.priority -eq [int]$candidate.Priority
            } | Select-Object -First 1)

            if ($exported.Count -gt 0 -and $null -ne $exported[0]) {
                $exported[0].id = ("CF-{0}-{1:000}" -f [string]$worksheet.Name, $definitions.Count + 1)
                $definitions += $exported[0]
                continue
            }

            $definitions += [pscustomobject]@{
                id = ("CF-{0}-{1:000}" -f [string]$worksheet.Name, $definitions.Count + 1)
                sheet = [string]$worksheet.Name
                type = "expression"
                address = [string]$appliesTo.Address()
                formula = [string]$candidate.Formula1
                priority = [int]$candidate.Priority
                stopIfTrue = [bool]$candidate.StopIfTrue
                format = [pscustomobject]@{
                    interiorColor = ('#{0:X6}' -f ([int]$candidate.Interior.Color -band 0xFFFFFF))
                    fontColor = ('#{0:X6}' -f ([int]$candidate.Font.Color -band 0xFFFFFF))
                    bold = [bool]$candidate.Font.Bold
                }
            }
        }
    }

    return @($definitions | Sort-Object sheet, priority, id)
}

function Invoke-PackageStructureWriteback {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ManifestPath,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [Parameter(Mandatory = $true)]
        [string]$Surface
    )

    [void](Invoke-PackageWorkbookHelper -Command 'sync' -ManifestPath $ManifestPath -WorkbookPath $WorkbookPath -Surface @($Surface) -Mode 'push' -Apply)
}

$resolved = Resolve-ExcelFoundryManifest -ManifestPath $ManifestPath -WorkbookPathOverride $WorkbookPath
if ($Direction -eq 'push' -and (Test-OoxmlPackageWorkbook -WorkbookPath $resolved.WorkbookPath)) {
    if ($resolved.Structure.FormulasPath) {
        Invoke-PackageStructureWriteback -ManifestPath $resolved.ManifestPath -WorkbookPath $resolved.WorkbookPath -Surface 'formulas'
        Write-Output ("PUSH FORMULAS => {0}" -f $resolved.Structure.FormulasPath)
    }
    if ($resolved.Structure.DataValidationPath) {
        Invoke-PackageStructureWriteback -ManifestPath $resolved.ManifestPath -WorkbookPath $resolved.WorkbookPath -Surface 'data-validation'
        Write-Output ("PUSH DATA-VALIDATION => {0}" -f $resolved.Structure.DataValidationPath)
    }
    if ($resolved.Structure.ProtectionPath) {
        Invoke-PackageStructureWriteback -ManifestPath $resolved.ManifestPath -WorkbookPath $resolved.WorkbookPath -Surface 'protection'
        Write-Output ("PUSH PROTECTION => {0}" -f $resolved.Structure.ProtectionPath)
    }
}
if ($Direction -eq 'pull') {
    try {
        $context = Open-ExcelWorkbook -WorkbookPath $resolved.WorkbookPath -Visible:$Visible
    }
    catch {
        if (-not (Test-OoxmlPackageWorkbook -WorkbookPath $resolved.WorkbookPath)) {
            throw
        }

        $queryPayload = Get-ExcelWorkbookQuery -WorkbookPath $resolved.WorkbookPath -Surface @('sheets', 'tables', 'names', 'cf', 'formulas', 'data-validation', 'protection', 'charts', 'pivots') -Backend 'package'
        Write-StructureArtifactsFromQueryPayload -ResolvedManifest $resolved -QueryPayload $queryPayload

        if ($resolved.Structure.SheetsPath) {
            Write-Output ("PULL SHEETS => {0}" -f $resolved.Structure.SheetsPath)
        }
        if ($resolved.Structure.TablesPath) {
            Write-Output ("PULL TABLES => {0}" -f $resolved.Structure.TablesPath)
        }
        if ($resolved.Structure.NamesPath) {
            Write-Output ("PULL NAMES => {0}" -f $resolved.Structure.NamesPath)
        }
        if ($resolved.Structure.ConditionalFormattingPath) {
            Write-Output ("PULL CF => {0}" -f $resolved.Structure.ConditionalFormattingPath)
        }
        if ($resolved.Structure.FormulasPath) {
            Write-Output ("PULL FORMULAS => {0}" -f $resolved.Structure.FormulasPath)
        }
        if ($resolved.Structure.DataValidationPath) {
            Write-Output ("PULL DATA-VALIDATION => {0}" -f $resolved.Structure.DataValidationPath)
        }
        if ($resolved.Structure.ProtectionPath) {
            Write-Output ("PULL PROTECTION => {0}" -f $resolved.Structure.ProtectionPath)
        }
        if ($resolved.Structure.ChartsPath) {
            Write-Output ("PULL CHARTS => {0}" -f $resolved.Structure.ChartsPath)
        }
        if ($resolved.Structure.PivotsPath) {
            Write-Output ("PULL PIVOTS => {0}" -f $resolved.Structure.PivotsPath)
        }
        if ($resolved.Structure.SlicersPath) {
            Write-Output ("PULL SLICERS => {0}" -f $resolved.Structure.SlicersPath)
        }
        if ($resolved.Structure.TimelinesPath) {
            Write-Output ("PULL TIMELINES => {0}" -f $resolved.Structure.TimelinesPath)
        }
        return
    }
}
else {
    $context = Open-ExcelWorkbook -WorkbookPath $resolved.WorkbookPath -Visible:$Visible
}

try {
    if ($resolved.Structure.TablesPath) {
        $tableArtifact = Read-JsonFile -Path $resolved.Structure.TablesPath
        if ($Direction -eq "push") {
            foreach ($table in @($tableArtifact.tables)) {
                Ensure-TableDefinition -Workbook $context.Workbook -TableSpec $table
                Write-Output ("PUSH TABLE {0}" -f $table.name)
            }
        }
        else {
            $discoveryMode = ""
            if ($null -ne $resolved.Structure.TablesDiscovery -and $null -ne $resolved.Structure.TablesDiscovery.PSObject.Properties["mode"]) {
                $discoveryMode = [string]$resolved.Structure.TablesDiscovery.mode
            }

            if ($discoveryMode -eq "all") {
                $tableArtifact.tables = @(Export-DiscoveredTableDefinitions -Workbook $context.Workbook -DiscoverySpec $resolved.Structure.TablesDiscovery)
            }
            else {
                $tableArtifact.tables = @($tableArtifact.tables | ForEach-Object {
                    Export-TableDefinition -Workbook $context.Workbook -TableSpec $_
                })
            }
            Write-JsonFile -Path $resolved.Structure.TablesPath -Value $tableArtifact
            Write-Output ("PULL TABLES => {0}" -f $resolved.Structure.TablesPath)
        }
    }

    if ($resolved.Structure.NamesPath) {
        $namesArtifact = Read-JsonFile -Path $resolved.Structure.NamesPath
        if ($Direction -eq "push") {
            foreach ($name in @($namesArtifact.names)) {
                Ensure-WorkbookName -Workbook $context.Workbook -NameSpec $name
                Write-Output ("PUSH NAME {0}" -f $name.name)
            }
        }
        else {
            $discoveryMode = ""
            if ($null -ne $resolved.Structure.NamesDiscovery -and $null -ne $resolved.Structure.NamesDiscovery.PSObject.Properties["mode"]) {
                $discoveryMode = [string]$resolved.Structure.NamesDiscovery.mode
            }

            if ($discoveryMode -eq "all") {
                $namesArtifact.names = @(Export-DiscoveredWorkbookNames -Workbook $context.Workbook -DiscoverySpec $resolved.Structure.NamesDiscovery)
            }
            else {
                $namesArtifact.names = @($namesArtifact.names | ForEach-Object {
                    Export-WorkbookName -Workbook $context.Workbook -NameSpec $_
                })
            }
            Write-JsonFile -Path $resolved.Structure.NamesPath -Value $namesArtifact
            Write-Output ("PULL NAMES => {0}" -f $resolved.Structure.NamesPath)
        }
    }

    if ($resolved.Structure.ConditionalFormattingPath) {
        $cfArtifact = Read-JsonFile -Path $resolved.Structure.ConditionalFormattingPath
        if ($Direction -eq "push") {
            $rulesBySheet = @{}
            foreach ($rule in @($cfArtifact.rules | Sort-Object sheet, priority, address, id)) {
                $sheetName = [string]$rule.sheet
                if (-not $rulesBySheet.ContainsKey($sheetName)) {
                    $rulesBySheet[$sheetName] = New-Object System.Collections.Generic.List[object]
                }
                $rulesBySheet[$sheetName].Add($rule)
            }

            foreach ($entry in $rulesBySheet.GetEnumerator()) {
                $worksheet = Get-WorksheetByName -Workbook $context.Workbook -WorksheetName $entry.Key
                Remove-SupportedFormatConditions -TargetRange $worksheet.Cells
                foreach ($rule in $entry.Value) {
                    Ensure-ConditionalFormatRule -Workbook $context.Workbook -RuleSpec $rule
                    Write-Output ("PUSH CF {0}" -f $rule.id)
                }
            }
        }
        else {
            $discoveryMode = ""
            if ($null -ne $resolved.Structure.ConditionalFormattingDiscovery -and $null -ne $resolved.Structure.ConditionalFormattingDiscovery.PSObject.Properties["mode"]) {
                $discoveryMode = [string]$resolved.Structure.ConditionalFormattingDiscovery.mode
            }

            if ($discoveryMode -eq "all-formula") {
                $cfArtifact.rules = @(Export-DiscoveredConditionalFormatRules -Workbook $context.Workbook -DiscoverySpec $resolved.Structure.ConditionalFormattingDiscovery | Where-Object { $_.type -eq "expression" })
            }
            elseif ($discoveryMode -eq "all" -or $discoveryMode -eq "all-major") {
                $cfArtifact.rules = @(Get-ConditionalFormattingQuery -Workbook $context.Workbook | Where-Object { $_.supported })
            }
            else {
                $cfArtifact.rules = @($cfArtifact.rules | ForEach-Object {
                    Export-ConditionalFormatRule -Workbook $context.Workbook -RuleSpec $_
                })
            }
            Write-JsonFile -Path $resolved.Structure.ConditionalFormattingPath -Value $cfArtifact
            Write-Output ("PULL CF => {0}" -f $resolved.Structure.ConditionalFormattingPath)
        }
    }

    if ($Direction -eq "push") {
        if ($resolved.Structure.ChartsPath) {
            $chartArtifact = Read-JsonFile -Path $resolved.Structure.ChartsPath
            foreach ($chart in @($chartArtifact.charts)) {
                Ensure-DirectChartDefinition -Workbook $context.Workbook -ChartSpec $chart -Mode 'set'
                Write-Output ("PUSH CHART {0}" -f $chart.name)
            }
        }
        if ($resolved.Structure.PivotsPath) {
            $pivotArtifact = Read-JsonFile -Path $resolved.Structure.PivotsPath
            foreach ($pivot in @($pivotArtifact.pivots)) {
                Ensure-DirectPivotDefinition -Workbook $context.Workbook -PivotSpec $pivot -Mode 'set'
                Write-Output ("PUSH PIVOT {0}" -f $pivot.name)
            }
        }
        if ($resolved.Structure.SlicersPath) {
            $slicerArtifact = Read-JsonFile -Path $resolved.Structure.SlicersPath
            foreach ($slicer in @($slicerArtifact.slicers)) {
                Ensure-DirectSlicerLikeDefinition -Workbook $context.Workbook -Spec $slicer -Mode 'set'
                Write-Output ("PUSH SLICER {0}" -f $slicer.name)
            }
        }
        if ($resolved.Structure.TimelinesPath) {
            $timelineArtifact = Read-JsonFile -Path $resolved.Structure.TimelinesPath
            foreach ($timeline in @($timelineArtifact.timelines)) {
                Ensure-DirectSlicerLikeDefinition -Workbook $context.Workbook -Spec $timeline -Mode 'set' -Timeline
                Write-Output ("PUSH TIMELINE {0}" -f $timeline.name)
            }
        }
    } else {
        $metadataSurfaces = @()
        if ($resolved.Structure.FormulasPath) {
            $metadataSurfaces += 'formulas'
        }
        if ($resolved.Structure.DataValidationPath) {
            $metadataSurfaces += 'data-validation'
        }
        if ($resolved.Structure.ProtectionPath) {
            $metadataSurfaces += 'protection'
        }
        if ($resolved.Structure.ChartsPath) {
            $metadataSurfaces += 'charts'
        }
        if ($resolved.Structure.PivotsPath) {
            $metadataSurfaces += 'pivots'
        }
        if ($resolved.Structure.SlicersPath) {
            $metadataSurfaces += 'slicers'
        }
        if ($resolved.Structure.TimelinesPath) {
            $metadataSurfaces += 'timelines'
        }
        if (@($metadataSurfaces).Count -gt 0) {
            $metadataPayload = Get-ExcelWorkbookQuery -WorkbookPath $resolved.WorkbookPath -Surface $metadataSurfaces -Backend 'auto'
            Write-StructureArtifactsFromQueryPayload -ResolvedManifest $resolved -QueryPayload $metadataPayload
            if ($resolved.Structure.FormulasPath) {
                Write-Output ("PULL FORMULAS => {0}" -f $resolved.Structure.FormulasPath)
            }
            if ($resolved.Structure.DataValidationPath) {
                Write-Output ("PULL DATA-VALIDATION => {0}" -f $resolved.Structure.DataValidationPath)
            }
            if ($resolved.Structure.ProtectionPath) {
                Write-Output ("PULL PROTECTION => {0}" -f $resolved.Structure.ProtectionPath)
            }
            if ($resolved.Structure.ChartsPath) {
                Write-Output ("PULL CHARTS => {0}" -f $resolved.Structure.ChartsPath)
            }
            if ($resolved.Structure.PivotsPath) {
                Write-Output ("PULL PIVOTS => {0}" -f $resolved.Structure.PivotsPath)
            }
            if ($resolved.Structure.SlicersPath) {
                Write-Output ("PULL SLICERS => {0}" -f $resolved.Structure.SlicersPath)
            }
            if ($resolved.Structure.TimelinesPath) {
                Write-Output ("PULL TIMELINES => {0}" -f $resolved.Structure.TimelinesPath)
            }
        }
    }

    $context.Workbook.Save()
}
finally {
    Close-ExcelWorkbook -Context $context -SaveChanges:$true
}
