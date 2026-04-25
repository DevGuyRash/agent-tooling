Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not ('Microsoft.VisualBasic.CompilerServices.NewLateBinding' -as [type])) {
    Add-Type -AssemblyName Microsoft.VisualBasic
}

function Resolve-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,
        [Parameter(Mandatory = $true)]
        [string]$RelativeOrAbsolutePath
    )

    if ([string]::IsNullOrWhiteSpace($RelativeOrAbsolutePath)) {
        return $RelativeOrAbsolutePath
    }

    if ([System.IO.Path]::IsPathRooted($RelativeOrAbsolutePath)) {
        return [System.IO.Path]::GetFullPath($RelativeOrAbsolutePath)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $RelativeOrAbsolutePath))
}

function Resolve-RelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,
        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $baseFullPath = [System.IO.Path]::GetFullPath($BasePath)
    if (-not $baseFullPath.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $baseFullPath += [System.IO.Path]::DirectorySeparatorChar
    }

    $targetFullPath = [System.IO.Path]::GetFullPath($TargetPath)
    $baseUri = [System.Uri]$baseFullPath
    $targetUri = [System.Uri]$targetFullPath
    if ($baseUri.Scheme -ne $targetUri.Scheme) {
        return $null
    }

    $relativeUri = $baseUri.MakeRelativeUri($targetUri)
    return [System.Uri]::UnescapeDataString($relativeUri.ToString()).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
}

function Get-LateProperty {
    param(
        [Parameter(Mandatory = $true)]
        $Target,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [object[]]$Arguments = @()
    )

    return [Microsoft.VisualBasic.CompilerServices.NewLateBinding]::LateGet(
        $Target,
        $null,
        $Name,
        $Arguments,
        $null,
        $null,
        $null
    )
}

function Invoke-LateMethod {
    param(
        [Parameter(Mandatory = $true)]
        $Target,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [object[]]$Arguments = @()
    )

    return [Microsoft.VisualBasic.CompilerServices.NewLateBinding]::LateCall(
        $Target,
        $null,
        $Name,
        $Arguments,
        $null,
        $null,
        $null,
        $true
    )
}

function Ensure-ParentDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
}

function Try-SetProperty {
    param(
        [Parameter(Mandatory = $true)]
        $Target,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        $Value
    )

    try {
        $Target.$Name = $Value
        return $true
    }
    catch {
        return $false
    }
}

function Test-IsRetriableExcelComException {
    param(
        [Parameter(Mandatory = $true)]
        [System.Exception]$Exception
    )

    $candidate = $Exception
    while ($null -ne $candidate) {
        if ($null -eq $candidate) {
            break
        }

        $hresult = $null
        try {
            $hresult = [int]$candidate.HResult
        }
        catch {
            $candidate = $candidate.InnerException
            continue
        }

        if ($hresult -in @(-2147418111, -2146777998)) {
            return $true
        }

        $candidate = $candidate.InnerException
    }

    return $false
}

function Invoke-ExcelComWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Operation,
        [string]$Description = 'Excel COM operation',
        [int]$MaxAttempts = 10,
        [int]$DelayMilliseconds = 300
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            return & $Operation
        }
        catch {
            if ($attempt -ge $MaxAttempts -or -not (Test-IsRetriableExcelComException -Exception $_.Exception)) {
                throw
            }
            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }

    throw "$Description failed after $MaxAttempts attempts."
}

function Release-ComObjectSafely {
    param(
        $Object
    )

    if ($null -ne $Object -and [System.Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($Object)
    }
}

function Invoke-ExcelQuitSafely {
    param(
        $Excel,
        [string]$Description = 'Quitting Excel',
        [switch]$SwallowErrors,
        [int]$MaxAttempts = 20,
        [int]$DelayMilliseconds = 500
    )

    if ($null -eq $Excel) {
        return
    }

    try {
        Invoke-ExcelComWithRetry -Description $Description -MaxAttempts $MaxAttempts -DelayMilliseconds $DelayMilliseconds -Operation {
            $Excel.Quit()
        } | Out-Null
    }
    catch {
        if (-not $SwallowErrors) {
            throw
        }
    }
}

function Read-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "JSON file not found: $Path"
    }

    return (ConvertFrom-JsonCompat -Json (Get-Content -Raw -LiteralPath $Path))
}

function ConvertFrom-JsonCompat {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Json
    )

    $convertFromJsonCommand = Get-Command -Name ConvertFrom-Json -ErrorAction Stop
    if ($convertFromJsonCommand.Parameters.ContainsKey('Depth')) {
        return ($Json | ConvertFrom-Json -Depth 100)
    }

    return ($Json | ConvertFrom-Json)
}

function ConvertTo-ProcessArgumentString {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Arguments
    )

    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($argument in @($Arguments)) {
        if ($null -eq $argument) {
            $parts.Add('""') | Out-Null
            continue
        }
        $text = [string]$argument
        if ($text.Length -eq 0) {
            $parts.Add('""') | Out-Null
            continue
        }
        if ($text -notmatch '[\s"]') {
            $parts.Add($text) | Out-Null
            continue
        }
        $escaped = $text -replace '(\\*)"', '$1$1\"'
        $escaped = $escaped -replace '(\\+)$', '$1$1'
        $parts.Add('"' + $escaped + '"') | Out-Null
    }

    return [string]::Join(' ', $parts)
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        $Value
    )

    Ensure-ParentDirectory -Path $Path
    $json = $Value | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}

function Write-TextFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    Ensure-ParentDirectory -Path $Path
    $normalized = $Value -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText($Path, $normalized, [System.Text.UTF8Encoding]::new($false))
}

function Normalize-ExcelFormulaForComparison {
    param(
        [AllowNull()]
        [string]$Formula
    )

    if ($null -eq $Formula) {
        return ""
    }

    $normalized = $Formula -replace "`r`n?", "`n"
    $normalized = (($normalized -split "`n") -join ' ') -replace '\s+', ' '
    return $normalized.Trim().ToUpperInvariant()
}

function Normalize-ConditionalFormatHexColor {
    param(
        [AllowNull()]
        [string]$Color
    )

    if ([string]::IsNullOrWhiteSpace($Color)) {
        return $null
    }

    $trimmed = $Color.Trim().ToUpperInvariant()
    if (-not $trimmed.StartsWith('#')) {
        $trimmed = "#$trimmed"
    }
    return $trimmed
}

function Get-ConditionalFormatComparableStyle {
    param(
        $Rule
    )

    $format = $null
    if ($null -ne $Rule -and $null -ne $Rule.PSObject.Properties['format']) {
        $format = $Rule.format
    }

    return [pscustomobject]@{
        interiorColor = if ($null -ne $format -and $null -ne $format.PSObject.Properties['interiorColor']) { Normalize-ConditionalFormatHexColor -Color ([string]$format.interiorColor) } else { $null }
        fontColor = if ($null -ne $format -and $null -ne $format.PSObject.Properties['fontColor']) { Normalize-ConditionalFormatHexColor -Color ([string]$format.fontColor) } else { $null }
        bold = if ($null -ne $format -and $null -ne $format.PSObject.Properties['bold']) { [Nullable[bool]]([bool]$format.bold) } else { $null }
    }
}

function Test-ConditionalFormatRuleSemanticMatch {
    param(
        [Parameter(Mandatory = $true)]
        $RuleSpec,
        [Parameter(Mandatory = $true)]
        $Candidate
    )

    if ([string]$Candidate.sheet -ne [string]$RuleSpec.sheet) {
        return $false
    }
    if ([string]$Candidate.address -ne [string]$RuleSpec.address) {
        return $false
    }
    if ($null -ne $RuleSpec.PSObject.Properties['type'] -and -not [string]::IsNullOrWhiteSpace([string]$RuleSpec.type)) {
        if (([string]$Candidate.type).Trim().ToLowerInvariant() -ne ([string]$RuleSpec.type).Trim().ToLowerInvariant()) {
            return $false
        }
    }
    if ($null -ne $RuleSpec.PSObject.Properties['formula']) {
        $candidateFormula = Normalize-ExcelFormulaForComparison -Formula ([string]$Candidate.formula)
        $ruleFormula = Normalize-ExcelFormulaForComparison -Formula ([string]$RuleSpec.formula)
        if ($candidateFormula -ne $ruleFormula) {
            return $false
        }
    }

    $candidateStyle = Get-ConditionalFormatComparableStyle -Rule $Candidate
    $ruleStyle = Get-ConditionalFormatComparableStyle -Rule $RuleSpec
    foreach ($styleProperty in @('interiorColor', 'fontColor', 'bold')) {
        $ruleValue = $ruleStyle.$styleProperty
        if ($null -eq $ruleValue) {
            continue
        }
        if ($candidateStyle.$styleProperty -ne $ruleValue) {
            return $false
        }
    }

    return $true
}

function Resolve-ConditionalFormatRuleMatch {
    param(
        [Parameter(Mandatory = $true)]
        $RuleSpec,
        [Parameter(Mandatory = $true)]
        [object[]]$Candidates
    )

    $matches = @($Candidates | Where-Object { Test-ConditionalFormatRuleSemanticMatch -RuleSpec $RuleSpec -Candidate $_ })
    if ($matches.Count -eq 0) {
        throw "Managed conditional formatting rule not found for $($RuleSpec.id)"
    }
    if ($matches.Count -eq 1) {
        return $matches[0]
    }

    $preferred = @($matches)
    if ($null -ne $RuleSpec.PSObject.Properties['priority'] -and $null -ne $RuleSpec.priority) {
        $targetPriority = [int]$RuleSpec.priority
        $preferred =
            @($matches |
                Sort-Object @{ Expression = { [Math]::Abs(([int]$_.priority) - $targetPriority) } }, @{ Expression = { [int]$_.priority } }, @{ Expression = { [string]$_.id } })
        if ($preferred.Count -gt 1) {
            $firstDistance = [Math]::Abs(([int]$preferred[0].priority) - $targetPriority)
            $secondDistance = [Math]::Abs(([int]$preferred[1].priority) - $targetPriority)
            if ($firstDistance -lt $secondDistance) {
                return $preferred[0]
            }
        }
    }

    $candidateSummary =
        @($preferred | ForEach-Object {
            "{0}|{1}|{2}|{3}" -f [string]$_.sheet, [string]$_.address, [string]$_.priority, (Normalize-ExcelFormulaForComparison -Formula ([string]$_.formula))
        }) -join "; "
    throw "Managed conditional formatting rule is ambiguous for $($RuleSpec.id): $candidateSummary"
}

function ConvertTo-ObjectArray {
    param(
        $Value
    )

    if ($null -eq $Value) {
        return ,@()
    }

    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        return ,@($Value)
    }

    return ,@($Value)
}

function Resolve-ExcelFoundryManifest {
    param(
        [string]$ManifestPath,
        [string]$WorkbookPathOverride,
        [switch]$AllowMissingManifestForInspectQuery
    )

    if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
        if (-not $AllowMissingManifestForInspectQuery) {
            throw "ManifestPath is required for sync commands."
        }
        if ([string]::IsNullOrWhiteSpace($WorkbookPathOverride)) {
            throw "Provide either -ManifestPath or -WorkbookPath."
        }

        return [pscustomobject]@{
            ManifestPath = $null
            ManifestDirectory = $null
            WorkbookPath = [System.IO.Path]::GetFullPath($WorkbookPathOverride)
            VbaComponents = @()
            Structure = [pscustomobject]@{
                TablesPath = $null
                NamesPath = $null
                ConditionalFormattingPath = $null
                TablesDiscovery = $null
                NamesDiscovery = $null
                ConditionalFormattingDiscovery = $null
            }
            PowerQuery = [pscustomobject]@{
                QueriesDirectory = $null
                QueriesPath = $null
                ConnectionsPath = $null
                ModelPath = $null
                RefreshPath = $null
            }
        }
    }

    $manifestFullPath = [System.IO.Path]::GetFullPath($ManifestPath)
    $manifestDir = Split-Path -Parent $manifestFullPath
    $manifest = Read-JsonFile -Path $manifestFullPath

    $resolvedWorkbookPath =
        if ([string]::IsNullOrWhiteSpace($WorkbookPathOverride)) {
            Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath $manifest.workbookPath
        }
        else {
            [System.IO.Path]::GetFullPath($WorkbookPathOverride)
        }

    $manifestVbaComponents = @()
    if ($null -ne $manifest.PSObject.Properties['vbaComponents']) {
        $manifestVbaComponents = @($manifest.vbaComponents)
    }
    $resolvedVbaComponents = @()
    foreach ($component in $manifestVbaComponents) {
        $kind = $null
        if ($null -ne $component.PSObject.Properties['kind']) {
            $kind = [string]$component.kind
        }
        $resolvedVbaComponents += [pscustomobject]@{
            Name = [string]$component.name
            Path = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$component.path)
            Kind = $kind
        }
    }

    $resolvedVbaProject = [pscustomobject]@{
        ProjectPath = $null
        ReferencesPath = $null
    }
    $manifestVbaProject = $null
    if ($null -ne $manifest.PSObject.Properties['vbaProject']) {
        $manifestVbaProject = $manifest.vbaProject
    }
    if ($null -ne $manifestVbaProject) {
        if ($null -ne $manifestVbaProject.PSObject.Properties['projectPath'] -and $null -ne $manifestVbaProject.projectPath) {
            $resolvedVbaProject.ProjectPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$manifestVbaProject.projectPath)
        }
        if ($null -ne $manifestVbaProject.PSObject.Properties['referencesPath'] -and $null -ne $manifestVbaProject.referencesPath) {
            $resolvedVbaProject.ReferencesPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$manifestVbaProject.referencesPath)
        }
    }

    $structure = $null
    if ($null -ne $manifest.PSObject.Properties['structure']) {
        $structure = $manifest.structure
    }
    $resolvedStructure = [pscustomobject]@{
        SheetsPath = $null
        TablesPath = $null
        NamesPath = $null
        ConditionalFormattingPath = $null
        FormulasPath = $null
        DataValidationPath = $null
        ProtectionPath = $null
        ChartsPath = $null
        PivotsPath = $null
        SlicersPath = $null
        TimelinesPath = $null
        TablesDiscovery = $null
        NamesDiscovery = $null
        ConditionalFormattingDiscovery = $null
    }

    if ($null -ne $structure) {
        if ($null -ne $structure.PSObject.Properties['sheetsPath'] -and $null -ne $structure.sheetsPath) {
            $resolvedStructure.SheetsPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.sheetsPath)
        }
        if ($null -ne $structure.PSObject.Properties['tablesPath'] -and $null -ne $structure.tablesPath) {
            $resolvedStructure.TablesPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.tablesPath)
        }
        if ($null -ne $structure.PSObject.Properties['namesPath'] -and $null -ne $structure.namesPath) {
            $resolvedStructure.NamesPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.namesPath)
        }
        if ($null -ne $structure.PSObject.Properties['conditionalFormattingPath'] -and $null -ne $structure.conditionalFormattingPath) {
            $resolvedStructure.ConditionalFormattingPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.conditionalFormattingPath)
        }
        if ($null -ne $structure.PSObject.Properties['formulasPath'] -and $null -ne $structure.formulasPath) {
            $resolvedStructure.FormulasPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.formulasPath)
        }
        if ($null -ne $structure.PSObject.Properties['dataValidationPath'] -and $null -ne $structure.dataValidationPath) {
            $resolvedStructure.DataValidationPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.dataValidationPath)
        }
        if ($null -ne $structure.PSObject.Properties['protectionPath'] -and $null -ne $structure.protectionPath) {
            $resolvedStructure.ProtectionPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.protectionPath)
        }
        if ($null -ne $structure.PSObject.Properties['chartsPath'] -and $null -ne $structure.chartsPath) {
            $resolvedStructure.ChartsPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.chartsPath)
        }
        if ($null -ne $structure.PSObject.Properties['pivotsPath'] -and $null -ne $structure.pivotsPath) {
            $resolvedStructure.PivotsPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.pivotsPath)
        }
        if ($null -ne $structure.PSObject.Properties['slicersPath'] -and $null -ne $structure.slicersPath) {
            $resolvedStructure.SlicersPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.slicersPath)
        }
        if ($null -ne $structure.PSObject.Properties['timelinesPath'] -and $null -ne $structure.timelinesPath) {
            $resolvedStructure.TimelinesPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.timelinesPath)
        }
        if ($null -ne $structure.PSObject.Properties['tablesDiscovery'] -and $null -ne $structure.tablesDiscovery) {
            $resolvedStructure.TablesDiscovery = $structure.tablesDiscovery
        }
        if ($null -ne $structure.PSObject.Properties['namesDiscovery'] -and $null -ne $structure.namesDiscovery) {
            $resolvedStructure.NamesDiscovery = $structure.namesDiscovery
        }
        if ($null -ne $structure.PSObject.Properties['conditionalFormattingDiscovery'] -and $null -ne $structure.conditionalFormattingDiscovery) {
            $resolvedStructure.ConditionalFormattingDiscovery = $structure.conditionalFormattingDiscovery
        }
    }

    $resolvedPowerQuery = [pscustomobject]@{
        QueriesDirectory = $null
        QueriesPath = $null
        ConnectionsPath = $null
        ModelPath = $null
        RefreshPath = $null
    }
    $powerQuery = $null
    if ($null -ne $manifest.PSObject.Properties['powerQuery']) {
        $powerQuery = $manifest.powerQuery
    }
    if ($null -ne $powerQuery) {
        if ($null -ne $powerQuery.PSObject.Properties['queriesDirectory'] -and $null -ne $powerQuery.queriesDirectory) {
            $resolvedPowerQuery.QueriesDirectory = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$powerQuery.queriesDirectory)
        }
        if ($null -ne $powerQuery.PSObject.Properties['queriesPath'] -and $null -ne $powerQuery.queriesPath) {
            $resolvedPowerQuery.QueriesPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$powerQuery.queriesPath)
        }
        if ($null -ne $powerQuery.PSObject.Properties['connectionsPath'] -and $null -ne $powerQuery.connectionsPath) {
            $resolvedPowerQuery.ConnectionsPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$powerQuery.connectionsPath)
        }
        if ($null -ne $powerQuery.PSObject.Properties['modelPath'] -and $null -ne $powerQuery.modelPath) {
            $resolvedPowerQuery.ModelPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$powerQuery.modelPath)
        }
        if ($null -ne $powerQuery.PSObject.Properties['refreshPath'] -and $null -ne $powerQuery.refreshPath) {
            $resolvedPowerQuery.RefreshPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$powerQuery.refreshPath)
        }
    }

    return [pscustomobject]@{
        ManifestPath = $manifestFullPath
        ManifestDirectory = $manifestDir
        WorkbookPath = $resolvedWorkbookPath
        VbaComponents = $resolvedVbaComponents
        VbaProject = $resolvedVbaProject
        Structure = $resolvedStructure
        PowerQuery = $resolvedPowerQuery
        Manifest = $manifest
    }
}

function Open-ExcelWorkbook {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [switch]$Visible,
        [switch]$ReadOnlyIntent
    )

    if (-not (Test-Path -LiteralPath $WorkbookPath)) {
        throw "Workbook not found: $WorkbookPath"
    }

    $excel = $null
    $workbook = $null
    $script:ExcelFoundryLastOpenDiagnostics = $null

    try {
        $excel = New-Object -ComObject Excel.Application
    }
    catch {
        throw "Excel COM automation is unavailable on this host."
    }

    $state = [ordered]@{
        Visible = $null
        DisplayAlerts = $null
        ScreenUpdating = $null
        EnableEvents = $null
        AskToUpdateLinks = $null
        AutomationSecurity = $null
    }

    foreach ($propertyName in @('Visible', 'DisplayAlerts', 'ScreenUpdating', 'EnableEvents', 'AskToUpdateLinks', 'AutomationSecurity')) {
        try {
            $state[$propertyName] = $excel.$propertyName
        }
        catch {
            $state[$propertyName] = $null
        }
    }

    [void](Try-SetProperty -Target $excel -Name 'Visible' -Value ([bool]$Visible))
    [void](Try-SetProperty -Target $excel -Name 'DisplayAlerts' -Value $false)
    [void](Try-SetProperty -Target $excel -Name 'ScreenUpdating' -Value $false)
    [void](Try-SetProperty -Target $excel -Name 'EnableEvents' -Value $false)
    [void](Try-SetProperty -Target $excel -Name 'AskToUpdateLinks' -Value $false)
    $automationSecurityChanged = Try-SetProperty -Target $excel -Name 'AutomationSecurity' -Value 3
    $openDescription = if ($ReadOnlyIntent) { "Opening workbook for read-only inspection" } else { "Opening workbook" }

    try {
        $workbook = Invoke-ExcelComWithRetry -Description $openDescription -MaxAttempts 20 -DelayMilliseconds 500 -Operation {
            $openAttemptResults = New-Object System.Collections.Generic.List[object]
            $openAttempts = @(
                @{
                    Label = if ($ReadOnlyIntent) { 'direct-open-readonly-default' } else { 'direct-open-default' }
                    Operation = { $excel.Workbooks.Open($WorkbookPath, 0, [bool]$ReadOnlyIntent, $null, $null, $null, $true, $null, $null, $false, $false) }
                }
            )
            if ($ReadOnlyIntent) {
                $readOnlyRecoveryAttempts = @(
                    @{
                        Label = 'direct-open-readonly-basic'
                        Operation = { $excel.Workbooks.Open($WorkbookPath, 0, $true) }
                    },
                    @{
                        Label = 'direct-open-readonly-local'
                        Operation = { $excel.Workbooks.Open($WorkbookPath, 0, $true, $null, $null, $null, $true, $null, $null, $false, $false, $null, $false, $true) }
                    },
                    @{
                        Label = 'direct-open-readonly-repair'
                        Operation = { $excel.Workbooks.Open($WorkbookPath, 0, $true, $null, $null, $null, $true, $null, $null, $false, $false, $null, $false, $true, 1) }
                    },
                    @{
                        Label = 'direct-open-readonly-extract'
                        Operation = { $excel.Workbooks.Open($WorkbookPath, 0, $true, $null, $null, $null, $true, $null, $null, $false, $false, $null, $false, $true, 2) }
                    }
                )
                $openAttempts += $readOnlyRecoveryAttempts
            }
            else {
                $openAttempts += @(
                    @{
                        Label = 'direct-open-no-args'
                        Operation = { $excel.Workbooks.Open($WorkbookPath) }
                    },
                    @{
                        Label = 'direct-open-standard'
                        Operation = { $excel.Workbooks.Open($WorkbookPath, 0, $false) }
                    },
                    @{
                        Label = 'direct-open-readonly'
                        Operation = { $excel.Workbooks.Open($WorkbookPath, $false, $true) }
                    }
                )
            }

            $lastOpenError = $null
            $openedWorkbook = $null
            foreach ($openAttempt in $openAttempts) {
                try {
                    $openedWorkbook = & $openAttempt.Operation
                    $openAttemptResults.Add([pscustomobject]@{
                        label = [string]$openAttempt.Label
                        succeeded = $true
                    }) | Out-Null
                    break
                }
                catch {
                    $lastOpenError = $_
                    $hresult = $null
                    try { $hresult = [int]$_.Exception.HResult } catch {}
                    $openAttemptResults.Add([pscustomobject]@{
                        label = [string]$openAttempt.Label
                        succeeded = $false
                        error = [string]$_.Exception.Message
                        exceptionType = [string]$_.Exception.GetType().FullName
                        hresult = $hresult
                        retriable = [bool](Test-IsRetriableExcelComException -Exception $_.Exception)
                    }) | Out-Null
                }
            }

            $script:ExcelFoundryLastOpenDiagnostics = [pscustomobject]@{
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                readOnlyIntent = [bool]$ReadOnlyIntent
                attempts = @($openAttemptResults.ToArray())
            }

            if ($null -ne $openedWorkbook) {
                return $openedWorkbook
            }

            if ($null -ne $lastOpenError) {
                throw $lastOpenError
            }
        }
    }
    catch {
        try {
            Invoke-ExcelQuitSafely -Excel $excel -Description "Quitting Excel after failed open" -SwallowErrors
        }
        finally {
            if ($null -ne $excel) {
                [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
            }
            [gc]::Collect()
            [gc]::WaitForPendingFinalizers()
        }
        throw
    }
    finally {
        if ($automationSecurityChanged -and $null -ne $state.AutomationSecurity) {
            [void](Try-SetProperty -Target $excel -Name 'AutomationSecurity' -Value $state.AutomationSecurity)
        }
    }

    if ($null -eq $workbook) {
        try {
            Invoke-ExcelQuitSafely -Excel $excel -Description "Quitting Excel after null workbook open" -SwallowErrors
        }
        catch {
        }
        finally {
            if ($null -ne $excel) {
                [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
            }
            [gc]::Collect()
            [gc]::WaitForPendingFinalizers()
        }
        throw "Excel returned a null workbook handle for: $WorkbookPath"
    }

    return [pscustomobject]@{
        Excel = $excel
        Workbook = $workbook
        State = [pscustomobject]$state
        ReadOnly = $(try { [bool]$workbook.ReadOnly } catch { $null })
        OpenDiagnostics = $script:ExcelFoundryLastOpenDiagnostics
    }
}

function New-UnsupportedSurfaceEntry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Surface,
        [Parameter(Mandatory = $true)]
        [string]$Backend,
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    return [pscustomobject]@{
        surface = $Surface
        backend = $Backend
        reason = $Reason
    }
}

function Add-UnsupportedSurface {
    param(
        [Parameter(Mandatory = $true)]
        $List,
        [Parameter(Mandatory = $true)]
        [string]$Surface,
        [Parameter(Mandatory = $true)]
        [string]$Backend,
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    $List.Add((New-UnsupportedSurfaceEntry -Surface $Surface -Backend $Backend -Reason $Reason)) | Out-Null
}

function Close-ExcelWorkbook {
    param(
        [Parameter(Mandatory = $true)]
        $Context,
        [bool]$SaveChanges = $true
    )

    $workbook = $Context.Workbook
    $excel = $Context.Excel
    $state = $null
    try { $state = $Context.State } catch {}

    try {
        if ($null -ne $workbook) {
            Invoke-ExcelComWithRetry -Description "Closing workbook" -Operation {
                $workbook.Close($SaveChanges)
            } | Out-Null
        }
    }
    finally {
        if ($null -ne $excel) {
            if ($null -ne $state) {
                foreach ($propertyName in @('AutomationSecurity', 'AskToUpdateLinks', 'EnableEvents', 'ScreenUpdating', 'DisplayAlerts', 'Visible')) {
                    if ($null -ne $state.$propertyName) {
                        [void](Try-SetProperty -Target $excel -Name $propertyName -Value $state.$propertyName)
                    }
                }
            }
            Invoke-ExcelQuitSafely -Excel $excel -Description "Quitting Excel"
        }
        Release-ComObjectSafely -Object $workbook
        Release-ComObjectSafely -Object $excel
        [gc]::Collect()
        [gc]::WaitForPendingFinalizers()
    }
}

function Resolve-VbaComponent {
    param(
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName
    )

    $vbProject = $Workbook.VBProject
    $vbComponents = $vbProject.VBComponents

    try {
        $direct = $vbComponents.Item($ComponentName)
        if ($null -ne $direct) {
            return $direct
        }
    }
    catch {
    }

    foreach ($component in $vbComponents) {
        try {
            if ([string]$component.Name -eq $ComponentName) {
                return $component
            }
        }
        catch {
        }
    }

    foreach ($worksheet in $Workbook.Worksheets) {
        try {
            $worksheetName = [string]$worksheet.Name
            $worksheetCodeName = [string]$worksheet.CodeName
            if (($worksheetName -eq $ComponentName) -or ($worksheetCodeName -eq $ComponentName)) {
                $sheetComponent = $vbComponents.Item($worksheetCodeName)
                if ($null -ne $sheetComponent) {
                    return $sheetComponent
                }
            }
        }
        catch {
        }
    }

    throw "Workbook VBA component not found: $ComponentName"
}

function Resolve-VbaComponentOrNull {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName
    )

    try {
        return Resolve-VbaComponent -Workbook $Workbook -ComponentName $ComponentName
    }
    catch {
        return $null
    }
}

function Ensure-VbaComponentExists {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName,
        [string]$PreferredType = "standard-module"
    )

    try {
        return Resolve-VbaComponent -Workbook $Workbook -ComponentName $ComponentName
    }
    catch {
    }

    foreach ($worksheet in $Workbook.Worksheets) {
        try {
            if (([string]$worksheet.Name -eq $ComponentName) -or ([string]$worksheet.CodeName -eq $ComponentName)) {
                return Resolve-VbaComponent -Workbook $Workbook -ComponentName ([string]$worksheet.CodeName)
            }
        }
        catch {
        }
    }

    $vbComponents = $Workbook.VBProject.VBComponents
    $componentType = switch ($PreferredType) {
        "class-module" { 2 }
        "user-form" { 3 }
        default { 1 }
    }
    $created = $vbComponents.Add($componentType)
    try {
        $created.Name = $ComponentName
    }
    catch {
    }
    return $created
}

function Get-VbComponentTypeName {
    param(
        [Parameter(Mandatory = $true)]
        $Component
    )

    $rawType = [int](Get-LateProperty -Target $Component -Name "Type")
    switch ($rawType) {
        1 { return "standard-module" }
        2 { return "class-module" }
        3 { return "user-form" }
        100 { return "document-module" }
        default { return "type-$rawType" }
    }
}

function Test-VbaComponentImportable {
    param(
        [Parameter(Mandatory = $true)]
        $Component
    )

    $kind = Get-VbComponentTypeName -Component $Component
    return $kind -in @("standard-module", "class-module", "user-form")
}

function Test-VbaModuleMutationSupported {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook
    )

    try {
        $vbProject = $Workbook.VBProject
        $vbComponents = $vbProject.VBComponents
        $component = $vbComponents.Add(1)
        try {
            $vbComponents.Remove($component)
        }
        catch {
        }
        return $true
    }
    catch {
        return $false
    }
}

function Remove-VbaComponentIfImportable {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName
    )

    $component = Ensure-VbaComponentExists -Workbook $Workbook -ComponentName $ComponentName
    if (-not (Test-VbaComponentImportable -Component $component)) {
        return
    }

    $vbComponents = $Workbook.VBProject.VBComponents
    $vbComponents.Remove($component)
}

function Set-VbaComponentCode {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName,
        [Parameter(Mandatory = $true)]
        [string]$SourcePath
    )

    if (-not (Test-Path -LiteralPath $SourcePath)) {
        throw "VBA source file not found: $SourcePath"
    }

    $component = Resolve-VbaComponentOrNull -Workbook $Workbook -ComponentName $ComponentName
    if ($null -eq $component) {
        $tempImportPath = Join-Path ([System.IO.Path]::GetTempPath()) ($ComponentName + ".bas")
        try {
            Copy-Item -LiteralPath $SourcePath -Destination $tempImportPath -Force
            $vbComponents = $Workbook.VBProject.VBComponents
            $component = $vbComponents.Import($tempImportPath)
            try { $component.Name = $ComponentName } catch {}
        }
        finally {
            if (Test-Path -LiteralPath $tempImportPath) {
                Remove-Item -LiteralPath $tempImportPath -Force
            }
        }
    }
    $module = Get-LateProperty -Target $component -Name "CodeModule"
    $sourceText = Get-Content -Raw -LiteralPath $SourcePath
    $lineCount = [int](Get-LateProperty -Target $module -Name "CountOfLines")

    if ($lineCount -gt 0) {
        Invoke-LateMethod -Target $module -Name "DeleteLines" -Arguments @(1, $lineCount) | Out-Null
    }

    if (-not [string]::IsNullOrWhiteSpace($sourceText)) {
        Invoke-LateMethod -Target $module -Name "AddFromString" -Arguments @($sourceText) | Out-Null
    }
}

function Copy-IfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    if (Test-Path -LiteralPath $SourcePath) {
        Ensure-ParentDirectory -Path $DestinationPath
        Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
    }
}

function Set-VbaComponentArtifact {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName,
        [Parameter(Mandatory = $true)]
        [string]$SourcePath
    )

    $extension = [System.IO.Path]::GetExtension($SourcePath).ToLowerInvariant()
    if ($extension -in @(".bas", ".cls", ".frm")) {
        if (-not (Test-Path -LiteralPath $SourcePath)) {
            throw "VBA source file not found: $SourcePath"
        }

        $component = Resolve-VbaComponentOrNull -Workbook $Workbook -ComponentName $ComponentName
        if ($null -eq $component) {
            $vbComponents = $Workbook.VBProject.VBComponents
            $imported = $vbComponents.Import($SourcePath)
            try {
                $imported.Name = $ComponentName
            }
            catch {
            }
            return
        }
        if (Test-VbaComponentImportable -Component $component) {
            Remove-VbaComponentIfImportable -Workbook $Workbook -ComponentName $ComponentName
            $vbComponents = $Workbook.VBProject.VBComponents
            $imported = $vbComponents.Import($SourcePath)
            try {
                $imported.Name = $ComponentName
            }
            catch {
            }
            return
        }
    }

    Set-VbaComponentCode -Workbook $Workbook -ComponentName $ComponentName -SourcePath $SourcePath
}

function Export-VbaComponentCode {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    $component = Resolve-VbaComponent -Workbook $Workbook -ComponentName $ComponentName
    $module = Get-LateProperty -Target $component -Name "CodeModule"
    $lineCount = [int](Get-LateProperty -Target $module -Name "CountOfLines")
    $sourceText =
        if ($lineCount -gt 0) {
            [string](Get-LateProperty -Target $module -Name "Lines" -Arguments @(1, $lineCount))
        }
        else {
            ""
        }

    Ensure-ParentDirectory -Path $DestinationPath
    [System.IO.File]::WriteAllText($DestinationPath, $sourceText, [System.Text.UTF8Encoding]::new($false))
}

function Export-VbaComponentArtifact {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    $component = Resolve-VbaComponent -Workbook $Workbook -ComponentName $ComponentName
    $extension = [System.IO.Path]::GetExtension($DestinationPath).ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($extension)) {
        $kind = Get-VbComponentTypeName -Component $component
        switch ($kind) {
            "standard-module" { $DestinationPath = "$DestinationPath.bas" }
            "class-module" { $DestinationPath = "$DestinationPath.cls" }
            "user-form" { $DestinationPath = "$DestinationPath.frm" }
            default { $DestinationPath = "$DestinationPath.vba" }
        }
        $extension = [System.IO.Path]::GetExtension($DestinationPath).ToLowerInvariant()
    }

    if ($extension -in @(".bas", ".cls", ".frm") -and (Test-VbaComponentImportable -Component $component)) {
        Ensure-ParentDirectory -Path $DestinationPath
        Invoke-LateMethod -Target $component -Name "Export" -Arguments @($DestinationPath) | Out-Null
        return $DestinationPath
    }

    Export-VbaComponentCode -Workbook $Workbook -ComponentName $ComponentName -DestinationPath $DestinationPath
    return $DestinationPath
}

function Get-VbaProjectArtifact {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook
    )

    $info = Get-VbaProjectInfo -Workbook $Workbook
    return [pscustomobject]@{
        accessible = $info.accessible
        error = $info.error
        components = @($info.components)
    }
}

function Get-VbaReferenceArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook
    )

    $info = Get-VbaProjectInfo -Workbook $Workbook
    return [pscustomobject]@{
        accessible = $info.accessible
        error = $info.error
        references = @($info.references)
    }
}

function Ensure-VbaReferences {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $ReferenceArtifact
    )

    $project = Get-LateProperty -Target $Workbook -Name "VBProject"
    $existingRefs = @{}
    foreach ($reference in (Get-LateProperty -Target $project -Name "References")) {
        $refName = [string](Get-LateProperty -Target $reference -Name "Name")
        $existingRefs[$refName] = $reference
    }

    $desired = @($ReferenceArtifact.references | Where-Object { -not $_.builtIn })
    $desiredNames = @($desired | ForEach-Object { [string]$_.name })
    $referencesCollection = Get-LateProperty -Target $project -Name "References"

    foreach ($pair in $existingRefs.GetEnumerator()) {
        $reference = $pair.Value
        $builtIn = $false
        try { $builtIn = [bool](Get-LateProperty -Target $reference -Name "BuiltIn") } catch {}
        if ($builtIn) {
            continue
        }
        if ($desiredNames -notcontains $pair.Key) {
            try {
                Invoke-LateMethod -Target $referencesCollection -Name "Remove" -Arguments @($reference) | Out-Null
            }
            catch {
            }
        }
    }

    foreach ($reference in $referencesCollection) {
        try {
            $existingRefs[[string](Get-LateProperty -Target $reference -Name "Name")] = $reference
        }
        catch {
        }
    }

    foreach ($referenceSpec in $desired) {
        $name = [string]$referenceSpec.name
        if ($existingRefs.ContainsKey($name)) {
            continue
        }
        $added = $false
        if ($null -ne $referenceSpec.guid -and -not [string]::IsNullOrWhiteSpace([string]$referenceSpec.guid)) {
            try {
                Invoke-LateMethod -Target $referencesCollection -Name "AddFromGuid" -Arguments @([string]$referenceSpec.guid, [int]$referenceSpec.major, [int]$referenceSpec.minor) | Out-Null
                $added = $true
            }
            catch {
            }
        }
        if (-not $added -and $null -ne $referenceSpec.fullPath -and -not [string]::IsNullOrWhiteSpace([string]$referenceSpec.fullPath)) {
            Invoke-LateMethod -Target $referencesCollection -Name "AddFromFile" -Arguments @([string]$referenceSpec.fullPath) | Out-Null
        }
    }
}

function Get-WorksheetByName {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$WorksheetName
    )

    return $Workbook.Worksheets.Item($WorksheetName)
}

function Get-ListObjectByName {
    param(
        [Parameter(Mandatory = $true)]
        $Worksheet,
        [Parameter(Mandatory = $true)]
        [string]$TableName
    )

    return $Worksheet.ListObjects.Item($TableName)
}

function Find-ListObjectByName {
    param(
        [Parameter(Mandatory = $true)]
        $Worksheet,
        [Parameter(Mandatory = $true)]
        [string]$TableName
    )

    foreach ($listObject in $Worksheet.ListObjects) {
        if ([string]$listObject.Name -eq $TableName) {
            return $listObject
        }
    }

    return $null
}

function Convert-ColorHexToBgrInt {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HexColor
    )

    $normalized = $HexColor.Trim()
    if ($normalized.StartsWith("#")) {
        $normalized = $normalized.Substring(1)
    }

    if ($normalized.Length -ne 6) {
        throw "Expected #RRGGBB color, got '$HexColor'"
    }

    $r = [Convert]::ToInt32($normalized.Substring(0, 2), 16)
    $g = [Convert]::ToInt32($normalized.Substring(2, 2), 16)
    $b = [Convert]::ToInt32($normalized.Substring(4, 2), 16)
    return ($r + ($g * 256) + ($b * 65536))
}

function Convert-BgrIntToHexColor {
    param(
        $ColorValue
    )

    if ($null -eq $ColorValue) {
        return $null
    }

    return ('#{0:X6}' -f ([int]$ColorValue -band 0xFFFFFF))
}

function Test-SurfaceRequested {
    param(
        [string[]]$Surface,
        [string]$Name
    )

    return (($Surface.Count -eq 0) -or ($Surface -contains $Name))
}

function Get-NormalizedSurfaceNames {
    param(
        [string[]]$Surface = @()
    )

    $aliases = @{
        'conditional-formatting' = 'cf'
        'conditional_formatting' = 'cf'
        'power-query' = 'pq'
        'power_query' = 'pq'
        'data_validation' = 'data-validation'
        'datavalidation' = 'data-validation'
        'timeline' = 'timelines'
        'slicer' = 'slicers'
    }

    return @(
        @($Surface) |
            ForEach-Object { $_ -split ',' } |
            ForEach-Object { $_.Trim().ToLowerInvariant() } |
            Where-Object { $_ } |
            ForEach-Object {
                if ($aliases.ContainsKey($_)) {
                    $aliases[$_]
                }
                else {
                    $_
                }
            }
    )
}

function Get-PythonLauncher {
    if (-not [string]::IsNullOrWhiteSpace($env:EXCEL_WORKBOOK_SYNC_PYTHON)) {
        return @($env:EXCEL_WORKBOOK_SYNC_PYTHON)
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        return @($py.Source, '-3.12')
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        return @($python.Source)
    }

    throw "Python runtime is required for package workbook fallback."
}

function Test-OoxmlPackageWorkbook {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath
    )

    $extension = [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant()
    if ($extension -notin @('.xlsx', '.xlsm', '.xltx', '.xltm', '.xlam')) {
        return $false
    }

    try {
        Add-Type -AssemblyName System.IO.Compression -ErrorAction SilentlyContinue | Out-Null
        $stream = [System.IO.File]::Open(
            $WorkbookPath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        try {
            $archive = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Read, $false)
            $archive.Dispose()
        }
        finally {
            $stream.Dispose()
        }
        return $true
    }
    catch {
        return $false
    }
}

function Invoke-PackageWorkbookHelper {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('query', 'inspect', 'inspect-lite', 'bootstrap', 'mutate-audit', 'plan', 'compare', 'sync', 'workbook-capabilities', 'workbook-clone', 'workbook-inspect', 'workbook-create', 'workbook-diff', 'workbook-metadata', 'manifest-validate', 'manifest-doctor', 'manifest-migrate', 'sheet-list', 'sheet-create', 'sheet-hide', 'sheet-unhide', 'sheet-very-hide', 'sheet-reorder', 'sheet-delete', 'name-list', 'name-set', 'name-delete', 'dimension-get', 'hyperlink-list', 'comment-list', 'print-get', 'formula-list', 'validation-list', 'protection-get', 'table-list', 'table-read', 'query-list', 'cell-get', 'cell-set', 'range-get', 'range-set')]
        [string]$Command,
        [string]$WorkbookPath,
        [string]$OtherWorkbookPath,
        [string]$ManifestPath,
        [string[]]$Surface = @(),
        [string]$OutputDir,
        [ValidateSet('push', 'pull', 'roundtrip')]
        [string]$Mode = 'push',
        [string[]]$Sheet = @(),
        [string[]]$Table = @(),
        [string[]]$Name = @(),
        [string[]]$NamePrefix = @(),
        [string[]]$QueryName = @(),
        [string]$Address,
        [string]$RangeRef,
        [string]$TargetPath,
        [string]$Index,
        [string]$ValueJson,
        [string]$ValuesJson,
        [string]$SpecJson,
        [string]$SpecFile,
        [string]$RefersTo,
        [switch]$Hidden,
        [string]$StateRoot,
        [switch]$Apply,
        [switch]$Destructive,
        [switch]$Deep,
        [int]$TimeoutSeconds = 120
    )

    $pythonCommand = @(Get-PythonLauncher)
    $scriptPath = Join-Path $PSScriptRoot 'excel_workbook_package.py'
    $arguments = @($scriptPath, $Command)
    if (-not [string]::IsNullOrWhiteSpace($WorkbookPath)) {
        $arguments += @('--workbook-path', $WorkbookPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($OtherWorkbookPath)) {
        $arguments += @('--other-workbook-path', $OtherWorkbookPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($ManifestPath)) {
        $arguments += @('--manifest-path', $ManifestPath)
    }
    if (@($Surface).Count -gt 0) {
        $arguments += @('--surface', (@($Surface) -join ','))
    }
    if ($Command -in @('plan', 'sync')) {
        $arguments += @('--mode', $Mode)
    }
    foreach ($sheetName in @($Sheet)) {
        $arguments += @('--sheet', $sheetName)
    }
    foreach ($tableName in @($Table)) {
        $arguments += @('--table', $tableName)
    }
    foreach ($nameEntry in @($Name)) {
        $arguments += @('--name', $nameEntry)
    }
    foreach ($prefix in @($NamePrefix)) {
        $arguments += @('--name-prefix', $prefix)
    }
    foreach ($queryEntry in @($QueryName)) {
        $arguments += @('--query-name', $queryEntry)
    }
    if (-not [string]::IsNullOrWhiteSpace($Address)) {
        $arguments += @('--address', $Address)
    }
    if (-not [string]::IsNullOrWhiteSpace($RangeRef)) {
        $arguments += @('--range-ref', $RangeRef)
    }
    if (-not [string]::IsNullOrWhiteSpace($TargetPath)) {
        $arguments += @('--target-path', $TargetPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($Index)) {
        $arguments += @('--index', $Index)
    }
    if (-not [string]::IsNullOrWhiteSpace($ValueJson)) {
        $arguments += @('--value-json', $ValueJson)
    }
    if (-not [string]::IsNullOrWhiteSpace($ValuesJson)) {
        $arguments += @('--values-json', $ValuesJson)
    }
    if (-not [string]::IsNullOrWhiteSpace($SpecJson)) {
        $arguments += @('--spec-json', $SpecJson)
    }
    if (-not [string]::IsNullOrWhiteSpace($SpecFile)) {
        $arguments += @('--spec-file', $SpecFile)
    }
    if (-not [string]::IsNullOrWhiteSpace($RefersTo)) {
        $arguments += @('--refers-to', $RefersTo)
    }
    if ($Hidden) {
        $arguments += '--hidden'
    }
    if (-not [string]::IsNullOrWhiteSpace($StateRoot)) {
        $arguments += @('--state-root', $StateRoot)
    }
    if ($Apply) {
        $arguments += '--apply'
    }
    if ($Destructive) {
        $arguments += '--destructive'
    }
    if ($Deep -and $Command -eq 'workbook-capabilities') {
        $arguments += '--deep'
    }
    if ($Command -eq 'bootstrap') {
        if ([string]::IsNullOrWhiteSpace($OutputDir)) {
            throw "OutputDir is required for bootstrap."
        }
        $arguments += @('--output-dir', $OutputDir)
    }

    $launcherArgs = @()
    if ($pythonCommand.Count -gt 1) {
        $launcherArgs = @($pythonCommand[1..($pythonCommand.Count - 1)])
    }

    $process = $null
    try {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $pythonCommand[0]
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $allArguments = @($launcherArgs + $arguments)
        if ($startInfo.PSObject.Properties.Name -contains 'ArgumentList') {
            foreach ($argument in $allArguments) {
                [void]$startInfo.ArgumentList.Add([string]$argument)
            }
        }
        else {
            $startInfo.Arguments = ConvertTo-ProcessArgumentString -Arguments $allArguments
        }

        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        if (-not $process.Start()) {
            throw ("Package workbook helper failed to start for {0}." -f $Command)
        }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                $process.Kill($true)
            }
            catch {
            }
            throw ("Package workbook helper timed out for {0} after {1} seconds." -f $Command, $TimeoutSeconds)
        }
        $process.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $parsedPayload = $null
        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            try {
                $parsedPayload = ConvertFrom-JsonCompat -Json $stdout
            }
            catch {
                $parsedPayload = $null
            }
        }
        if ($process.ExitCode -ne 0) {
            if ($null -ne $parsedPayload) {
                return $parsedPayload
            }
            $details = @($stderr, $stdout) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
            if (@($details).Count -gt 0) {
                throw ("Package workbook helper failed for {0}: {1}" -f $Command, (($details -join [Environment]::NewLine).Trim()))
            }
            throw ("Package workbook helper failed for {0}." -f $Command)
        }
        if ([string]::IsNullOrWhiteSpace($stdout)) {
            throw ("Package workbook helper returned no JSON for {0}." -f $Command)
        }
        if ($null -ne $parsedPayload) {
            return $parsedPayload
        }
        return (ConvertFrom-JsonCompat -Json $stdout)
    }
    finally {
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
}

function Get-ManifestRelativeWorkbookPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ManifestDirectory,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath
    )

    $relative = Resolve-RelativePath -BasePath $ManifestDirectory -TargetPath $WorkbookPath
    if ([string]::IsNullOrWhiteSpace($relative)) {
        return [System.IO.Path]::GetFullPath($WorkbookPath)
    }

    return ($relative -replace '\\', '/')
}

function Write-ExcelWorkbookBootstrapArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [Parameter(Mandatory = $true)]
        [string]$OutputDir,
        [string]$ManifestPath,
        [Parameter(Mandatory = $true)]
        $QueryPayload
    )

    $outputRoot = [System.IO.Path]::GetFullPath($OutputDir)
    if (-not (Test-Path -LiteralPath $outputRoot)) {
        New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
    }

    if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
        $ManifestPath = Join-Path $outputRoot 'excel-sync.manifest.json'
    }

    $manifestDirectory = Split-Path -Parent ([System.IO.Path]::GetFullPath($ManifestPath))
    if (-not (Test-Path -LiteralPath $manifestDirectory)) {
        New-Item -ItemType Directory -Path $manifestDirectory -Force | Out-Null
    }

    $structureRoot = Join-Path $manifestDirectory 'workbook_structure'
    $sheetsPath = Join-Path $structureRoot 'sheets.json'
    $tablesPath = Join-Path $structureRoot 'tables.json'
    $namesPath = Join-Path $structureRoot 'names.json'
    $cfPath = Join-Path $structureRoot 'conditional_formatting.json'
    $formulasPath = Join-Path $structureRoot 'formulas.json'
    $dataValidationPath = Join-Path $structureRoot 'data_validation.json'
    $protectionPath = Join-Path $structureRoot 'protection.json'
    $chartsPath = Join-Path $structureRoot 'charts.json'
    $pivotsPath = Join-Path $structureRoot 'pivots.json'
    $slicersPath = Join-Path $structureRoot 'slicers.json'
    $timelinesPath = Join-Path $structureRoot 'timelines.json'

    Write-JsonFile -Path $sheetsPath -Value ([pscustomobject]@{ sheets = if ($null -ne $QueryPayload.PSObject.Properties['sheets']) { @($QueryPayload.sheets) } else { @() } })
    Write-JsonFile -Path $tablesPath -Value ([pscustomobject]@{ tables = @($QueryPayload.tables) })
    Write-JsonFile -Path $namesPath -Value ([pscustomobject]@{ names = @($QueryPayload.names) })
    Write-JsonFile -Path $cfPath -Value ([pscustomobject]@{ rules = @($QueryPayload.cf) })
    Write-JsonFile -Path $formulasPath -Value ([pscustomobject]@{ formulas = if ($null -ne $QueryPayload.PSObject.Properties['formulas']) { @($QueryPayload.formulas) } else { @() } })
    Write-JsonFile -Path $dataValidationPath -Value ([pscustomobject]@{ rules = if ($null -ne $QueryPayload.PSObject.Properties['dataValidation']) { @($QueryPayload.dataValidation) } else { @() } })
    Write-JsonFile -Path $protectionPath -Value ($(if ($null -ne $QueryPayload.PSObject.Properties['protection']) { $QueryPayload.protection } else { [pscustomobject]@{ workbook = $null; worksheets = @() } }))
    Write-JsonFile -Path $chartsPath -Value ([pscustomobject]@{ charts = if ($null -ne $QueryPayload.PSObject.Properties['charts']) { @($QueryPayload.charts) } else { @() } })
    Write-JsonFile -Path $pivotsPath -Value ([pscustomobject]@{ pivots = if ($null -ne $QueryPayload.PSObject.Properties['pivots']) { @($QueryPayload.pivots) } else { @() } })
    Write-JsonFile -Path $slicersPath -Value ([pscustomobject]@{ slicers = if ($null -ne $QueryPayload.PSObject.Properties['slicers']) { @($QueryPayload.slicers) } else { @() } })
    Write-JsonFile -Path $timelinesPath -Value ([pscustomobject]@{ timelines = if ($null -ne $QueryPayload.PSObject.Properties['timelines']) { @($QueryPayload.timelines) } else { @() } })

    $manifest = [ordered]@{
        workbookPath = Get-ManifestRelativeWorkbookPath -ManifestDirectory $manifestDirectory -WorkbookPath $WorkbookPath
        vbaComponents = @()
        structure = [ordered]@{
            sheetsPath = 'workbook_structure/sheets.json'
            tablesPath = 'workbook_structure/tables.json'
            namesPath = 'workbook_structure/names.json'
            conditionalFormattingPath = 'workbook_structure/conditional_formatting.json'
            formulasPath = 'workbook_structure/formulas.json'
            dataValidationPath = 'workbook_structure/data_validation.json'
            protectionPath = 'workbook_structure/protection.json'
            chartsPath = 'workbook_structure/charts.json'
            pivotsPath = 'workbook_structure/pivots.json'
            slicersPath = 'workbook_structure/slicers.json'
            timelinesPath = 'workbook_structure/timelines.json'
            tablesDiscovery = [ordered]@{ mode = 'all' }
            namesDiscovery = [ordered]@{
                mode = 'all'
                excludeBuiltIn = $true
            }
            conditionalFormattingDiscovery = [ordered]@{ mode = 'all-major' }
        }
    }

    $pq = @()
    $connections = @()
    $modelTables = @()
    $measures = @()
    $relationships = @()
    $hierarchies = @()
    $kpis = @()
    $perspectives = @()
    if ($null -ne $QueryPayload.PSObject.Properties['pq']) { $pq = @($QueryPayload.pq) }
    if ($null -ne $QueryPayload.PSObject.Properties['connections']) { $connections = @($QueryPayload.connections) }
    if ($null -ne $QueryPayload.PSObject.Properties['model']) {
        if ($null -ne $QueryPayload.model.PSObject.Properties['modelTables']) {
            $modelTables = @($QueryPayload.model.modelTables)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['measures']) {
            $measures = @($QueryPayload.model.measures)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['relationships']) {
            $relationships = @($QueryPayload.model.relationships)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['hierarchies']) {
            $hierarchies = @($QueryPayload.model.hierarchies)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['kpis']) {
            $kpis = @($QueryPayload.model.kpis)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['perspectives']) {
            $perspectives = @($QueryPayload.model.perspectives)
        }
    }

    if ($pq.Count -gt 0 -or $connections.Count -gt 0 -or $modelTables.Count -gt 0 -or $measures.Count -gt 0 -or $relationships.Count -gt 0 -or $hierarchies.Count -gt 0 -or $kpis.Count -gt 0 -or $perspectives.Count -gt 0) {
        $powerQueryDirectory = Join-Path $manifestDirectory 'power_query'
        $queryDirectory = Join-Path $powerQueryDirectory 'queries'
        if (-not (Test-Path -LiteralPath $queryDirectory)) {
            New-Item -ItemType Directory -Path $queryDirectory -Force | Out-Null
        }

        $usedNames = @{}
        $queryEntries = @()
        foreach ($query in $pq) {
            $baseName = ConvertTo-SafeArtifactFileName -Name ([string]$query.name)
            $fileName = "$baseName.pq"
            $suffix = 1
            while ($usedNames.ContainsKey($fileName)) {
                $fileName = "{0}-{1}.pq" -f $baseName, $suffix
                $suffix++
            }
            $usedNames[$fileName] = $true
            Write-TextFile -Path (Join-Path $queryDirectory $fileName) -Value ([string]$query.formula)
            $queryEntries += [pscustomobject]@{
                name = [string]$query.name
                file = $fileName
                description = if ($null -ne $query.PSObject.Properties['description']) { [string]$query.description } else { '' }
                connectionName = if ($null -ne $query.PSObject.Properties['connectionName']) { $query.connectionName } else { $null }
                loads = if ($null -ne $query.PSObject.Properties['loads']) { @($query.loads) } else { @() }
                loadToDataModel = if ($null -ne $query.PSObject.Properties['loadToDataModel']) { [bool]$query.loadToDataModel } else { $false }
            }
        }

        Write-JsonFile -Path (Join-Path $powerQueryDirectory 'queries.json') -Value ([pscustomobject]@{ queries = $queryEntries })
        Write-JsonFile -Path (Join-Path $powerQueryDirectory 'connections.json') -Value ([pscustomobject]@{ connections = $connections })
        Write-JsonFile -Path (Join-Path $powerQueryDirectory 'model.json') -Value ([pscustomobject]@{
            modelTables = $modelTables
            measures = $measures
            relationships = $relationships
            hierarchies = $hierarchies
            kpis = $kpis
            perspectives = $perspectives
        })
        Write-JsonFile -Path (Join-Path $powerQueryDirectory 'refresh.json') -Value ([pscustomobject]@{
            queries = @($pq | ForEach-Object {
                [pscustomobject]@{
                    name = [string]$_.name
                    connectionName = if ($null -ne $_.PSObject.Properties['connectionName']) { $_.connectionName } else { $null }
                }
            })
        })

        $manifest['powerQuery'] = [ordered]@{
            queriesDirectory = 'power_query/queries'
            queriesPath = 'power_query/queries.json'
            connectionsPath = 'power_query/connections.json'
            modelPath = 'power_query/model.json'
            refreshPath = 'power_query/refresh.json'
        }
    }

    Write-JsonFile -Path $ManifestPath -Value $manifest

    return [pscustomobject]@{
        manifestPath = [System.IO.Path]::GetFullPath($ManifestPath)
        manifestAliases = @([System.IO.Path]::GetFullPath($ManifestPath))
        outputDirectory = $outputRoot
        backend = if ($null -ne $QueryPayload.PSObject.Properties['backend']) { [string]$QueryPayload.backend } else { 'excel' }
        sourceFormat = [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant()
        workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
        warnings = if ($null -ne $QueryPayload.PSObject.Properties['warnings']) { ConvertTo-ObjectArray -Value $QueryPayload.warnings } else { @() }
        stagesTried = if ($null -ne $QueryPayload.PSObject.Properties['stagesTried']) { ConvertTo-ObjectArray -Value $QueryPayload.stagesTried } else { @() }
        capabilities = if ($null -ne $QueryPayload.PSObject.Properties['capabilities']) { $QueryPayload.capabilities } else { $null }
        unsupported = if ($null -ne $QueryPayload.PSObject.Properties['unsupported']) { ConvertTo-ObjectArray -Value $QueryPayload.unsupported } else { @() }
    }
}

function Write-StructureArtifactsFromQueryPayload {
    param(
        [Parameter(Mandatory = $true)]
        $ResolvedManifest,
        [Parameter(Mandatory = $true)]
        $QueryPayload
    )

    $structure = $ResolvedManifest.Structure
    if ($null -eq $structure) {
        return
    }

    $sheets = @()
    $tables = @()
    $names = @()
    $rules = @()
    $formulas = @()
    $dataValidation = @()
    $protection = [pscustomobject]@{
        workbook = $null
        worksheets = @()
    }
    $charts = @()
    $pivots = @()
    $slicers = @()
    $timelines = @()
    $slicers = @()
    $timelines = @()

    if ($null -ne $QueryPayload.PSObject.Properties['sheets']) {
        $sheets = @($QueryPayload.sheets)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['tables']) {
        $tables = @($QueryPayload.tables)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['names']) {
        $names = @($QueryPayload.names)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['cf']) {
        $rules = @($QueryPayload.cf)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['formulas']) {
        $formulas = @($QueryPayload.formulas)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['dataValidation']) {
        $dataValidation = @($QueryPayload.dataValidation)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['protection']) {
        $protection = $QueryPayload.protection
    }
    if ($null -ne $QueryPayload.PSObject.Properties['charts']) {
        $charts = @($QueryPayload.charts)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['pivots']) {
        $pivots = @($QueryPayload.pivots)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['slicers']) {
        $slicers = @($QueryPayload.slicers)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['timelines']) {
        $timelines = @($QueryPayload.timelines)
    }

    if (-not [string]::IsNullOrWhiteSpace($structure.SheetsPath)) {
        Write-JsonFile -Path $structure.SheetsPath -Value ([pscustomobject]@{ sheets = $sheets })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.TablesPath)) {
        Write-JsonFile -Path $structure.TablesPath -Value ([pscustomobject]@{ tables = $tables })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.NamesPath)) {
        Write-JsonFile -Path $structure.NamesPath -Value ([pscustomobject]@{ names = $names })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.ConditionalFormattingPath)) {
        Write-JsonFile -Path $structure.ConditionalFormattingPath -Value ([pscustomobject]@{ rules = $rules })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.FormulasPath)) {
        Write-JsonFile -Path $structure.FormulasPath -Value ([pscustomobject]@{ formulas = $formulas })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.DataValidationPath)) {
        Write-JsonFile -Path $structure.DataValidationPath -Value ([pscustomobject]@{ rules = $dataValidation })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.ProtectionPath)) {
        Write-JsonFile -Path $structure.ProtectionPath -Value $protection
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.ChartsPath)) {
        Write-JsonFile -Path $structure.ChartsPath -Value ([pscustomobject]@{ charts = $charts })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.PivotsPath)) {
        Write-JsonFile -Path $structure.PivotsPath -Value ([pscustomobject]@{ pivots = $pivots })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.SlicersPath)) {
        Write-JsonFile -Path $structure.SlicersPath -Value ([pscustomobject]@{ slicers = $slicers })
    }
    if (-not [string]::IsNullOrWhiteSpace($structure.TimelinesPath)) {
        Write-JsonFile -Path $structure.TimelinesPath -Value ([pscustomobject]@{ timelines = $timelines })
    }
}

function Get-ConnectionTypeName {
    param($Connection)

    try {
        $rawType = [int]$Connection.Type
    }
    catch {
        return $null
    }

    switch ($rawType) {
        1 { return "ole-db" }
        2 { return "odbc" }
        3 { return "worksheet" }
        4 { return "text" }
        5 { return "web" }
        6 { return "model" }
        default { return "type-$rawType" }
    }
}

function ConvertTo-SafeArtifactFileName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $safe = $Name
    foreach ($char in [System.IO.Path]::GetInvalidFileNameChars()) {
        $safe = $safe.Replace([string]$char, "_")
    }
    $safe = $safe -replace '[\\/:\*\?"<>\|]', '_'
    $safe = $safe.Trim()
    if ([string]::IsNullOrWhiteSpace($safe)) {
        return "query"
    }
    return $safe
}

function Get-WorkbookConnectionArtifacts {
    param($Workbook)

    $artifacts = @()
    foreach ($connection in $Workbook.Connections) {
        $entry = [ordered]@{
            name = [string]$connection.Name
            type = Get-ConnectionTypeName -Connection $connection
            rawType = $null
            description = $null
            oledb = $null
            model = $null
            worksheetDataConnection = $null
        }
        try { $entry.rawType = [int]$connection.Type } catch {}
        try { $entry.description = [string]$connection.Description } catch {}
        try {
            $oledb = $connection.OLEDBConnection
            if ($null -ne $oledb) {
                $entry.oledb = [ordered]@{
                    connection = $null
                    commandText = $null
                    commandType = $null
                    backgroundQuery = $null
                    refreshOnFileOpen = $null
                    refreshWithRefreshAll = $null
                    enableRefresh = $null
                }
                try { $entry.oledb.connection = [string]$oledb.Connection } catch {}
                try { $entry.oledb.commandText = [string]$oledb.CommandText } catch {}
                try { $entry.oledb.commandType = [string]$oledb.CommandType } catch {}
                try { $entry.oledb.backgroundQuery = [bool]$oledb.BackgroundQuery } catch {}
                try { $entry.oledb.refreshOnFileOpen = [bool]$oledb.RefreshOnFileOpen } catch {}
                try { $entry.oledb.refreshWithRefreshAll = [bool]$oledb.RefreshWithRefreshAll } catch {}
                try { $entry.oledb.enableRefresh = [bool]$oledb.EnableRefresh } catch {}
            }
        }
        catch {
        }
        try {
            $modelConnection = $connection.ModelConnection
            if ($null -ne $modelConnection) {
                $entry.model = [ordered]@{
                    commandText = $null
                    commandType = $null
                }
                try { $entry.model.commandText = [string]$modelConnection.CommandText } catch {}
                try { $entry.model.commandType = [string]$modelConnection.CommandType } catch {}
            }
        }
        catch {
        }
        try {
            $worksheetDataConnection = $connection.WorksheetDataConnection
            if ($null -ne $worksheetDataConnection) {
                $entry.worksheetDataConnection = [ordered]@{
                    name = $null
                }
                try { $entry.worksheetDataConnection.name = [string]$worksheetDataConnection.Name } catch {}
            }
        }
        catch {
        }
        $artifacts += [pscustomobject]$entry
    }

    return @($artifacts | Sort-Object name)
}

function Get-WorkbookQueryLoadArtifacts {
    param($Workbook)

    $loads = @()
    foreach ($worksheet in $Workbook.Worksheets) {
        foreach ($listObject in $worksheet.ListObjects) {
            try {
                $queryTable = $listObject.QueryTable
            }
            catch {
                $queryTable = $null
            }
            if ($null -eq $queryTable) {
                continue
            }

            $connectionName = $null
            try { $connectionName = [string]$queryTable.WorkbookConnection.Name } catch {}
            if ([string]::IsNullOrWhiteSpace($connectionName)) {
                continue
            }

            $loads += [pscustomobject]@{
                connectionName = $connectionName
                destinationType = 'worksheet-table'
                sheet = [string]$worksheet.Name
                table = [string]$listObject.Name
                topLeft = [string]$listObject.Range.Cells.Item(1, 1).Address($false, $false)
            }
        }
    }

    return @($loads | Sort-Object connectionName, sheet, table)
}

function Get-WorkbookModelRelationshipId {
    param(
        [string]$ForeignKeyTable,
        [string]$ForeignKeyColumn,
        [string]$PrimaryKeyTable,
        [string]$PrimaryKeyColumn
    )

    return ("{0}[{1}]->{2}[{3}]" -f $ForeignKeyTable, $ForeignKeyColumn, $PrimaryKeyTable, $PrimaryKeyColumn)
}

function Get-OptionalModelProperty {
    param(
        [Parameter(Mandatory = $true)]
        $Target,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [object[]]$Arguments = @()
    )

    if ($null -eq $Target) {
        return $null
    }

    try {
        if ($Arguments.Count -gt 0) {
            return Get-LateProperty -Target $Target -Name $Name -Arguments $Arguments
        }
        return $Target.$Name
    }
    catch {
        try {
            return Get-LateProperty -Target $Target -Name $Name -Arguments $Arguments
        }
        catch {
            return $null
        }
    }
}

function Get-OptionalModelCollection {
    param(
        [Parameter(Mandatory = $true)]
        $Target,
        [Parameter(Mandatory = $true)]
        [string[]]$CandidateNames
    )

    foreach ($candidate in $CandidateNames) {
        $value = Get-OptionalModelProperty -Target $Target -Name $candidate
        if ($null -ne $value) {
            return @($value)
        }
    }

    return @()
}

function Get-WorkbookModelHierarchyId {
    param(
        [string]$AssociatedTable,
        [string]$HierarchyName
    )

    if ([string]::IsNullOrWhiteSpace($AssociatedTable)) {
        return [string]$HierarchyName
    }

    return ("{0}[{1}]" -f $AssociatedTable, $HierarchyName)
}

function Get-WorkbookModelArtifacts {
    param($Workbook)

    $model = $null
    try {
        $model = $Workbook.Model
    }
    catch {
        return [pscustomobject]@{
            modelTables = @()
            measures = @()
            relationships = @()
            hierarchies = @()
            kpis = @()
            perspectives = @()
        }
    }

    $tables = @()
    try {
        foreach ($modelTable in $model.ModelTables) {
            $entry = [ordered]@{
                name = $null
                sourceName = $null
                recordCount = $null
                columns = @()
            }
            try { $entry.name = [string]$modelTable.Name } catch {}
            try { $entry.sourceName = [string]$modelTable.SourceName } catch {}
            try { $entry.recordCount = [int]$modelTable.RecordCount } catch {}
            $columns = @()
            try {
                foreach ($column in $modelTable.ModelTableColumns) {
                    $columnEntry = [ordered]@{
                        name = $null
                        dataType = $null
                    }
                    try { $columnEntry.name = [string]$column.Name } catch {}
                    try { $columnEntry.dataType = [string]$column.DataType } catch {}
                    $columns += [pscustomobject]$columnEntry
                }
            }
            catch {
            }
            $entry.columns = @($columns | Sort-Object name)
            $tables += [pscustomobject]$entry
        }
    }
    catch {
    }

    $measures = @()
    try {
        foreach ($measure in $model.ModelMeasures) {
            $entry = [ordered]@{
                name = $null
                formula = $null
                description = $null
                associatedTable = $null
            }
            try { $entry.name = [string]$measure.Name } catch {}
            try { $entry.formula = [string]$measure.Formula } catch {}
            try { $entry.description = [string]$measure.Description } catch {}
            try { $entry.associatedTable = [string]$measure.AssociatedTable.Name } catch {}
            $measures += [pscustomobject]$entry
        }
    }
    catch {
    }

    $relationships = @()
    try {
        foreach ($relationship in $model.ModelRelationships) {
            $entry = [ordered]@{
                id = $null
                foreignKeyTable = $null
                foreignKeyColumn = $null
                primaryKeyTable = $null
                primaryKeyColumn = $null
            }
            try { $entry.foreignKeyTable = [string]$relationship.ForeignKeyTable.Name } catch {}
            try { $entry.foreignKeyColumn = [string]$relationship.ForeignKeyColumn.Name } catch {}
            try { $entry.primaryKeyTable = [string]$relationship.PrimaryKeyTable.Name } catch {}
            try { $entry.primaryKeyColumn = [string]$relationship.PrimaryKeyColumn.Name } catch {}
            $entry.id = Get-WorkbookModelRelationshipId `
                -ForeignKeyTable ([string]$entry.foreignKeyTable) `
                -ForeignKeyColumn ([string]$entry.foreignKeyColumn) `
                -PrimaryKeyTable ([string]$entry.primaryKeyTable) `
                -PrimaryKeyColumn ([string]$entry.primaryKeyColumn)
            $relationships += [pscustomobject]$entry
        }
    }
    catch {
    }

    $hierarchies = @()
    try {
        foreach ($hierarchy in (Get-OptionalModelCollection -Target $model -CandidateNames @('ModelHierarchies', 'Hierarchies'))) {
            $entry = [ordered]@{
                id = $null
                name = $null
                associatedTable = $null
                description = $null
                hidden = $null
                levels = @()
            }
            try { $entry.name = [string](Get-OptionalModelProperty -Target $hierarchy -Name 'Name') } catch {}
            try { $entry.associatedTable = [string](Get-OptionalModelProperty -Target (Get-OptionalModelProperty -Target $hierarchy -Name 'AssociatedTable') -Name 'Name') } catch {}
            try { $entry.description = [string](Get-OptionalModelProperty -Target $hierarchy -Name 'Description') } catch {}
            try {
                $hiddenValue = Get-OptionalModelProperty -Target $hierarchy -Name 'Hidden'
                if ($null -ne $hiddenValue) {
                    $entry.hidden = [bool]$hiddenValue
                }
            }
            catch {}

            $levels = @()
            foreach ($level in (Get-OptionalModelCollection -Target $hierarchy -CandidateNames @('HierarchyLevels', 'Levels'))) {
                $levelEntry = [ordered]@{
                    name = $null
                    sourceColumn = $null
                    ordinal = $null
                }
                try { $levelEntry.name = [string](Get-OptionalModelProperty -Target $level -Name 'Name') } catch {}
                try { $levelEntry.sourceColumn = [string](Get-OptionalModelProperty -Target (Get-OptionalModelProperty -Target $level -Name 'SourceColumn') -Name 'Name') } catch {}
                try {
                    $ordinalValue = Get-OptionalModelProperty -Target $level -Name 'Ordinal'
                    if ($null -ne $ordinalValue) {
                        $levelEntry.ordinal = [int]$ordinalValue
                    }
                }
                catch {}
                $levels += [pscustomobject]$levelEntry
            }
            $entry.levels = @($levels | Sort-Object ordinal, name)
            $entry.id = Get-WorkbookModelHierarchyId -AssociatedTable ([string]$entry.associatedTable) -HierarchyName ([string]$entry.name)
            $hierarchies += [pscustomobject]$entry
        }
    }
    catch {
    }

    $kpis = @()
    try {
        foreach ($kpi in (Get-OptionalModelCollection -Target $model -CandidateNames @('ModelKpis', 'KPIs', 'Kpis'))) {
            $entry = [ordered]@{
                name = $null
                description = $null
                associatedMeasure = $null
                associatedTable = $null
                statusExpression = $null
                targetExpression = $null
                trendExpression = $null
                statusGraphic = $null
                targetGraphic = $null
            }
            try { $entry.name = [string](Get-OptionalModelProperty -Target $kpi -Name 'Name') } catch {}
            try { $entry.description = [string](Get-OptionalModelProperty -Target $kpi -Name 'Description') } catch {}
            try {
                $associatedMeasure = Get-OptionalModelProperty -Target $kpi -Name 'AssociatedMeasure'
                if ($null -eq $associatedMeasure) {
                    $associatedMeasure = Get-OptionalModelProperty -Target $kpi -Name 'Measure'
                }
                $entry.associatedMeasure = [string](Get-OptionalModelProperty -Target $associatedMeasure -Name 'Name')
                $entry.associatedTable = [string](Get-OptionalModelProperty -Target (Get-OptionalModelProperty -Target $associatedMeasure -Name 'AssociatedTable') -Name 'Name')
            }
            catch {}
            foreach ($propertyName in @('StatusExpression', 'TargetExpression', 'TrendExpression', 'StatusGraphic', 'TargetGraphic')) {
                try {
                    $entry[$propertyName.Substring(0,1).ToLowerInvariant() + $propertyName.Substring(1)] = [string](Get-OptionalModelProperty -Target $kpi -Name $propertyName)
                }
                catch {}
            }
            $kpis += [pscustomobject]$entry
        }
    }
    catch {
    }

    $perspectives = @()
    try {
        foreach ($perspective in (Get-OptionalModelCollection -Target $model -CandidateNames @('ModelPerspectives', 'Perspectives'))) {
            $entry = [ordered]@{
                name = $null
                tables = @()
                measures = @()
                hierarchies = @()
            }
            try { $entry.name = [string](Get-OptionalModelProperty -Target $perspective -Name 'Name') } catch {}
            $entry.tables = @(
                (Get-OptionalModelCollection -Target $perspective -CandidateNames @('ModelTables', 'Tables') |
                    ForEach-Object {
                        try { [string](Get-OptionalModelProperty -Target $_ -Name 'Name') } catch { $null }
                    } |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
                    Sort-Object -Unique)
            )
            $entry.measures = @(
                (Get-OptionalModelCollection -Target $perspective -CandidateNames @('ModelMeasures', 'Measures') |
                    ForEach-Object {
                        try { [string](Get-OptionalModelProperty -Target $_ -Name 'Name') } catch { $null }
                    } |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
                    Sort-Object -Unique)
            )
            $entry.hierarchies = @(
                (Get-OptionalModelCollection -Target $perspective -CandidateNames @('ModelHierarchies', 'Hierarchies') |
                    ForEach-Object {
                        try { [string](Get-OptionalModelProperty -Target $_ -Name 'Name') } catch { $null }
                    } |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
                    Sort-Object -Unique)
            )
            $perspectives += [pscustomobject]$entry
        }
    }
    catch {
    }

    return [pscustomobject]@{
        modelTables = @($tables | Sort-Object name)
        measures = @($measures | Sort-Object name)
        relationships = @($relationships | Sort-Object id)
        hierarchies = @($hierarchies | Sort-Object id, name)
        kpis = @($kpis | Sort-Object name)
        perspectives = @($perspectives | Sort-Object name)
    }
}

function Get-WorkbookPowerQueryArtifacts {
    param($Workbook)

    $connections = @(Get-WorkbookConnectionArtifacts -Workbook $Workbook)
    $loads = @(Get-WorkbookQueryLoadArtifacts -Workbook $Workbook)
    $modelArtifacts = Get-WorkbookModelArtifacts -Workbook $Workbook
    $modelTables = @($modelArtifacts.modelTables)
    $modelNames = @($modelTables | ForEach-Object { [string]$_.name })
    $queries = @()

    foreach ($query in $Workbook.Queries) {
        $queryName = [string]$query.Name
        $preferredConnectionName = "Query - $queryName"
        $connectionName = $null
        if (@($connections | Where-Object { $_.name -eq $preferredConnectionName }).Count -gt 0) {
            $connectionName = $preferredConnectionName
        }
        elseif (@($connections | Where-Object { $_.name -eq $queryName }).Count -gt 0) {
            $connectionName = $queryName
        }

        $queryLoads = @()
        if (-not [string]::IsNullOrWhiteSpace($connectionName)) {
            $queryLoads = @($loads | Where-Object { $_.connectionName -eq $connectionName })
        }

        $queries += [pscustomobject]@{
            name = $queryName
            description = $(try { [string]$query.Description } catch { $null })
            formula = [string]$query.Formula
            connectionName = $connectionName
            loads = @($queryLoads)
            loadToDataModel = ($modelNames -contains $queryName)
        }
    }

    return [pscustomobject]@{
        queries = @($queries | Sort-Object name)
        connections = $connections
        modelTables = $modelTables
        measures = @($modelArtifacts.measures)
        relationships = @($modelArtifacts.relationships)
        hierarchies = @($modelArtifacts.hierarchies)
        kpis = @($modelArtifacts.kpis)
        perspectives = @($modelArtifacts.perspectives)
    }
}

function Find-WorkbookModelTable {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$TableName
    )

    try {
        foreach ($modelTable in $Workbook.Model.ModelTables) {
            if ([string]$modelTable.Name -eq $TableName) {
                return $modelTable
            }
        }
    }
    catch {
    }

    return $null
}

function Find-WorkbookModelColumn {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$TableName,
        [Parameter(Mandatory = $true)]
        [string]$ColumnName
    )

    $modelTable = Find-WorkbookModelTable -Workbook $Workbook -TableName $TableName
    if ($null -eq $modelTable) {
        return $null
    }

    try {
        foreach ($column in $modelTable.ModelTableColumns) {
            if ([string]$column.Name -eq $ColumnName) {
                return $column
            }
        }
    }
    catch {
    }

    return $null
}

function Find-WorkbookModelMeasure {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$MeasureName
    )

    try {
        foreach ($measure in $Workbook.Model.ModelMeasures) {
            if ([string]$measure.Name -eq $MeasureName) {
                return $measure
            }
        }
    }
    catch {
    }

    return $null
}

function Find-WorkbookModelRelationship {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$RelationshipId
    )

    try {
        foreach ($relationship in $Workbook.Model.ModelRelationships) {
            $candidateId = Get-WorkbookModelRelationshipId `
                -ForeignKeyTable ([string]$relationship.ForeignKeyTable.Name) `
                -ForeignKeyColumn ([string]$relationship.ForeignKeyColumn.Name) `
                -PrimaryKeyTable ([string]$relationship.PrimaryKeyTable.Name) `
                -PrimaryKeyColumn ([string]$relationship.PrimaryKeyColumn.Name)
            if ($candidateId -eq $RelationshipId) {
                return $relationship
            }
        }
    }
    catch {
    }

    return $null
}

function Ensure-WorkbookModelMeasure {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $MeasureSpec
    )

    $measureName = [string]$MeasureSpec.name
    if ([string]::IsNullOrWhiteSpace($measureName)) {
        throw "Model measure spec requires a name."
    }
    $formula = if ($null -ne $MeasureSpec.PSObject.Properties['formula']) { [string]$MeasureSpec.formula } else { $null }
    if ([string]::IsNullOrWhiteSpace($formula)) {
        throw "Model measure spec requires a formula."
    }
    $associatedTableName =
        if ($null -ne $MeasureSpec.PSObject.Properties['associatedTable'] -and -not [string]::IsNullOrWhiteSpace([string]$MeasureSpec.associatedTable)) {
            [string]$MeasureSpec.associatedTable
        }
        elseif ($null -ne $MeasureSpec.PSObject.Properties['table'] -and -not [string]::IsNullOrWhiteSpace([string]$MeasureSpec.table)) {
            [string]$MeasureSpec.table
        }
        else {
            throw "Model measure spec requires associatedTable or table."
        }

    $associatedTable = Find-WorkbookModelTable -Workbook $Workbook -TableName $associatedTableName
    if ($null -eq $associatedTable) {
        throw "Model table not found: $associatedTableName"
    }

    $existing = Find-WorkbookModelMeasure -Workbook $Workbook -MeasureName $measureName
    if ($null -ne $existing) {
        try { $existing.Formula = $formula } catch {}
        if ($null -ne $MeasureSpec.PSObject.Properties['description']) {
            try { $existing.Description = [string]$MeasureSpec.description } catch {}
        }
        return $existing
    }

    $arguments = @(
        $measureName,
        $associatedTable,
        $formula
    )
    if ($null -ne $MeasureSpec.PSObject.Properties['formatInformation']) {
        $arguments += $MeasureSpec.formatInformation
    }
    else {
        $arguments += $null
    }
    if ($null -ne $MeasureSpec.PSObject.Properties['description']) {
        $arguments += [string]$MeasureSpec.description
    }
    else {
        $arguments += $null
    }

    return Invoke-LateMethod -Target $Workbook.Model.ModelMeasures -Name 'Add' -Arguments $arguments
}

function Remove-WorkbookModelMeasure {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$MeasureName
    )

    $measure = Find-WorkbookModelMeasure -Workbook $Workbook -MeasureName $MeasureName
    if ($null -eq $measure) {
        return $false
    }

    Invoke-LateMethod -Target $measure -Name 'Delete' | Out-Null
    return $true
}

function Ensure-WorkbookModelRelationship {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $RelationshipSpec
    )

    $fkTable = [string]$RelationshipSpec.foreignKeyTable
    $fkColumn = [string]$RelationshipSpec.foreignKeyColumn
    $pkTable = [string]$RelationshipSpec.primaryKeyTable
    $pkColumn = [string]$RelationshipSpec.primaryKeyColumn
    if ([string]::IsNullOrWhiteSpace($fkTable) -or [string]::IsNullOrWhiteSpace($fkColumn) -or [string]::IsNullOrWhiteSpace($pkTable) -or [string]::IsNullOrWhiteSpace($pkColumn)) {
        throw "Model relationship spec requires foreignKeyTable, foreignKeyColumn, primaryKeyTable, and primaryKeyColumn."
    }

    $relationshipId = Get-WorkbookModelRelationshipId -ForeignKeyTable $fkTable -ForeignKeyColumn $fkColumn -PrimaryKeyTable $pkTable -PrimaryKeyColumn $pkColumn
    $existing = Find-WorkbookModelRelationship -Workbook $Workbook -RelationshipId $relationshipId
    if ($null -ne $existing) {
        return $existing
    }

    $foreignKey = Find-WorkbookModelColumn -Workbook $Workbook -TableName $fkTable -ColumnName $fkColumn
    if ($null -eq $foreignKey) {
        throw "Foreign-key column not found: $fkTable[$fkColumn]"
    }
    $primaryKey = Find-WorkbookModelColumn -Workbook $Workbook -TableName $pkTable -ColumnName $pkColumn
    if ($null -eq $primaryKey) {
        throw "Primary-key column not found: $pkTable[$pkColumn]"
    }

    return Invoke-LateMethod -Target $Workbook.Model.ModelRelationships -Name 'Add' -Arguments @($foreignKey, $primaryKey)
}

function Remove-WorkbookModelRelationship {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$RelationshipId
    )

    $relationship = Find-WorkbookModelRelationship -Workbook $Workbook -RelationshipId $RelationshipId
    if ($null -eq $relationship) {
        return $false
    }

    Invoke-LateMethod -Target $relationship -Name 'Delete' | Out-Null
    return $true
}

function Get-PowerQueryRefreshArtifacts {
    param(
        [object[]]$Connections = @(),
        [object[]]$Queries = @()
    )

    $items = @()
    foreach ($connection in @($Connections)) {
        $oledb = $null
        if ($null -ne $connection.PSObject.Properties['oledb']) {
            $oledb = $connection.oledb
        }

        if ($null -eq $oledb -or $null -eq $oledb.PSObject.Properties['connection']) {
            continue
        }

        if ([string]$oledb.connection -notlike 'OLEDB;Provider=Microsoft.Mashup.OleDb.1*') {
            continue
        }

        $items += [pscustomobject]@{
            connectionName = [string]$connection.name
            backgroundQuery = if ($null -ne $oledb.PSObject.Properties['backgroundQuery']) { $oledb.backgroundQuery } else { $null }
            refreshOnFileOpen = if ($null -ne $oledb.PSObject.Properties['refreshOnFileOpen']) { $oledb.refreshOnFileOpen } else { $null }
            refreshWithRefreshAll = if ($null -ne $oledb.PSObject.Properties['refreshWithRefreshAll']) { $oledb.refreshWithRefreshAll } else { $null }
        }
    }

    if ($items.Count -eq 0 -and @($Queries).Count -gt 0) {
        $items = @($Queries | ForEach-Object {
            [pscustomobject]@{
                name = [string]$_.name
                connectionName = if ($null -ne $_.PSObject.Properties['connectionName']) { $_.connectionName } else { $null }
            }
        })
    }

    return @($items)
}

function Write-PowerQueryArtifactsFromPayload {
    param(
        [Parameter(Mandatory = $true)]
        $ResolvedManifest,
        [Parameter(Mandatory = $true)]
        $QueryPayload
    )

    $powerQuery = $ResolvedManifest.PowerQuery
    if ($null -eq $powerQuery) {
        return
    }

    $queries = @()
    $connections = @()
    $modelTables = @()
    $measures = @()
    $relationships = @()
    $hierarchies = @()
    $kpis = @()
    $perspectives = @()

    if ($null -ne $QueryPayload.PSObject.Properties['pq']) {
        $queries = @($QueryPayload.pq)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['connections']) {
        $connections = @($QueryPayload.connections)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['model']) {
        if ($null -ne $QueryPayload.model.PSObject.Properties['modelTables']) {
            $modelTables = @($QueryPayload.model.modelTables)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['measures']) {
            $measures = @($QueryPayload.model.measures)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['relationships']) {
            $relationships = @($QueryPayload.model.relationships)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['hierarchies']) {
            $hierarchies = @($QueryPayload.model.hierarchies)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['kpis']) {
            $kpis = @($QueryPayload.model.kpis)
        }
        if ($null -ne $QueryPayload.model.PSObject.Properties['perspectives']) {
            $perspectives = @($QueryPayload.model.perspectives)
        }
    }

    $entries = @()
    $usedFiles = @{}
    foreach ($query in $queries) {
        $baseName = ConvertTo-SafeArtifactFileName -Name ([string]$query.name)
        $fileName = "$baseName.pq"
        $suffix = 1
        while ($usedFiles.ContainsKey($fileName)) {
            $fileName = "{0}-{1}.pq" -f $baseName, $suffix
            $suffix++
        }
        $usedFiles[$fileName] = $true

        if (-not [string]::IsNullOrWhiteSpace($powerQuery.QueriesDirectory)) {
            Write-TextFile -Path (Join-Path $powerQuery.QueriesDirectory $fileName) -Value ([string]$query.formula)
        }

        $entries += [pscustomobject]@{
            name = [string]$query.name
            file = $fileName
            description = if ($null -ne $query.PSObject.Properties['description']) { $query.description } else { $null }
            connectionName = if ($null -ne $query.PSObject.Properties['connectionName']) { $query.connectionName } else { $null }
            loads = if ($null -ne $query.PSObject.Properties['loads']) { @($query.loads) } else { @() }
            loadToDataModel = if ($null -ne $query.PSObject.Properties['loadToDataModel']) { [bool]$query.loadToDataModel } else { $false }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($powerQuery.QueriesPath)) {
        Write-JsonFile -Path $powerQuery.QueriesPath -Value ([pscustomobject]@{ queries = @($entries) })
    }
    if (-not [string]::IsNullOrWhiteSpace($powerQuery.ConnectionsPath)) {
        Write-JsonFile -Path $powerQuery.ConnectionsPath -Value ([pscustomobject]@{ connections = @($connections) })
    }
    if (-not [string]::IsNullOrWhiteSpace($powerQuery.ModelPath)) {
        Write-JsonFile -Path $powerQuery.ModelPath -Value ([pscustomobject]@{
            modelTables = @($modelTables)
            measures = @($measures)
            relationships = @($relationships)
            hierarchies = @($hierarchies)
            kpis = @($kpis)
            perspectives = @($perspectives)
        })
    }
    if (-not [string]::IsNullOrWhiteSpace($powerQuery.RefreshPath)) {
        $items = @(Get-PowerQueryRefreshArtifacts -Connections $connections -Queries $queries)
        Write-JsonFile -Path $powerQuery.RefreshPath -Value ([pscustomobject]@{ items = @($items) })
    }
}

function Export-PowerQueryArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $ResolvedManifest
    )

    $powerQuery = $ResolvedManifest.PowerQuery
    if ($null -eq $powerQuery) {
        return
    }

    $artifacts = Get-WorkbookPowerQueryArtifacts -Workbook $Workbook
    $payload = [pscustomobject]@{
        pq = @($artifacts.queries)
        connections = @($artifacts.connections)
        model = [pscustomobject]@{
            modelTables = @($artifacts.modelTables)
            measures = @($artifacts.measures)
            relationships = @($artifacts.relationships)
            hierarchies = @($artifacts.hierarchies)
            kpis = @($artifacts.kpis)
            perspectives = @($artifacts.perspectives)
        }
    }
    Write-PowerQueryArtifactsFromPayload -ResolvedManifest $ResolvedManifest -QueryPayload $payload
}

function Read-PowerQueryArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        $ResolvedManifest
    )

    $powerQuery = $ResolvedManifest.PowerQuery
    $queryEntries = @()
    $connections = @()
    $modelTables = @()
    $measures = @()
    $relationships = @()
    $hierarchies = @()
    $kpis = @()
    $perspectives = @()
    $refreshItems = @()

    if (-not [string]::IsNullOrWhiteSpace($powerQuery.QueriesPath) -and (Test-Path -LiteralPath $powerQuery.QueriesPath)) {
        $queryRoot = Read-JsonFile -Path $powerQuery.QueriesPath
        if ($null -ne $queryRoot.PSObject.Properties['queries']) {
            $queryEntries = @($queryRoot.queries)
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($powerQuery.ConnectionsPath) -and (Test-Path -LiteralPath $powerQuery.ConnectionsPath)) {
        $connectionRoot = Read-JsonFile -Path $powerQuery.ConnectionsPath
        if ($null -ne $connectionRoot.PSObject.Properties['connections']) {
            $connections = @($connectionRoot.connections)
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($powerQuery.ModelPath) -and (Test-Path -LiteralPath $powerQuery.ModelPath)) {
        $modelRoot = Read-JsonFile -Path $powerQuery.ModelPath
        if ($null -ne $modelRoot.PSObject.Properties['modelTables']) { $modelTables = @($modelRoot.modelTables) }
        if ($null -ne $modelRoot.PSObject.Properties['measures']) { $measures = @($modelRoot.measures) }
        if ($null -ne $modelRoot.PSObject.Properties['relationships']) { $relationships = @($modelRoot.relationships) }
        if ($null -ne $modelRoot.PSObject.Properties['hierarchies']) { $hierarchies = @($modelRoot.hierarchies) }
        if ($null -ne $modelRoot.PSObject.Properties['kpis']) { $kpis = @($modelRoot.kpis) }
        if ($null -ne $modelRoot.PSObject.Properties['perspectives']) { $perspectives = @($modelRoot.perspectives) }
    }
    if (-not [string]::IsNullOrWhiteSpace($powerQuery.RefreshPath) -and (Test-Path -LiteralPath $powerQuery.RefreshPath)) {
        $refreshRoot = Read-JsonFile -Path $powerQuery.RefreshPath
        if ($null -ne $refreshRoot.PSObject.Properties['items']) {
            $refreshItems = @($refreshRoot.items)
        }
    }

    $queries = @()
    foreach ($entry in $queryEntries) {
        $queryPath = $null
        $queryFile = $null
        if ($null -ne $entry.PSObject.Properties['file'] -and -not [string]::IsNullOrWhiteSpace([string]$entry.file)) {
            $queryFile = [string]$entry.file
        }
        elseif (-not [string]::IsNullOrWhiteSpace([string]$entry.name)) {
            $queryFile = ([string]$entry.name) + '.pq'
        }

        if (-not [string]::IsNullOrWhiteSpace($powerQuery.QueriesDirectory) -and -not [string]::IsNullOrWhiteSpace($queryFile)) {
            $queryPath = Join-Path $powerQuery.QueriesDirectory $queryFile
            if (-not (Test-Path -LiteralPath $queryPath) -and $queryPath.ToLowerInvariant().EndsWith('.pq')) {
                $fallback = $queryPath.Substring(0, $queryPath.Length - 3) + '.m'
                if (Test-Path -LiteralPath $fallback) {
                    $queryPath = $fallback
                }
            }
            if (-not (Test-Path -LiteralPath $queryPath)) {
                throw "Power Query file not found: $queryPath"
            }
        }

        $queries += [pscustomobject]@{
            name = [string]$entry.name
            description = $(if ($null -ne $entry.PSObject.Properties['description']) { $entry.description } else { $null })
            formula = $(if ($null -ne $queryPath) { Get-Content -Raw -LiteralPath $queryPath } else { $null })
            connectionName = $(if ($null -ne $entry.PSObject.Properties['connectionName']) { [string]$entry.connectionName } else { $null })
            loads = $(if ($null -ne $entry.PSObject.Properties['loads']) { @($entry.loads) } else { @() })
            loadToDataModel = $(if ($null -ne $entry.PSObject.Properties['loadToDataModel']) { [bool]$entry.loadToDataModel } else { $false })
        }
    }

    return [pscustomobject]@{
        queries = @($queries)
        connections = @($connections)
        modelTables = @($modelTables)
        measures = @($measures)
        relationships = @($relationships)
        hierarchies = @($hierarchies)
        kpis = @($kpis)
        perspectives = @($perspectives)
        refreshItems = @($refreshItems)
    }
}

function Find-WorkbookConnectionByName {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ConnectionName
    )

    foreach ($connection in $Workbook.Connections) {
        if ([string]$connection.Name -eq $ConnectionName) {
            return $connection
        }
    }

    return $null
}

function Read-JsonSpecValue {
    param(
        [string]$SpecJson,
        [string]$SpecFile
    )

    if (-not [string]::IsNullOrWhiteSpace($SpecJson) -and -not [string]::IsNullOrWhiteSpace($SpecFile)) {
        throw "Provide either SpecJson or SpecFile, not both."
    }

    if (-not [string]::IsNullOrWhiteSpace($SpecJson)) {
        return (ConvertFrom-JsonCompat -Json $SpecJson)
    }

    if (-not [string]::IsNullOrWhiteSpace($SpecFile)) {
        return Read-JsonFile -Path $SpecFile
    }

    return $null
}

function Get-DirectWorkbookItemByName {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Items,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    foreach ($item in @($Items)) {
        if ([string]$item.name -eq $Name) {
            return $item
        }
    }

    return $null
}

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

    $rowCount = @($Values).Count
    $colCount = @($Values[0]).Count
    $target = $Range.Resize($rowCount, $colCount)
    $matrix = New-Object 'object[,]' $rowCount, $colCount
    for ($r = 0; $r -lt $rowCount; $r++) {
        for ($c = 0; $c -lt $colCount; $c++) {
            $matrix[$r, $c] = @($Values[$r])[$c]
        }
    }
    $target.Value2 = $matrix

    return $target
}

function Convert-ColumnNumberToLetters {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ColumnNumber
    )

    $value = $ColumnNumber
    $letters = ""
    while ($value -gt 0) {
        $remainder = ($value - 1) % 26
        $letters = [char](65 + $remainder) + $letters
        $value = [math]::Floor(($value - 1) / 26)
    }
    return $letters
}

function Convert-ColumnLettersToNumber {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Letters
    )

    $value = 0
    foreach ($character in $Letters.ToUpperInvariant().ToCharArray()) {
        $value = ($value * 26) + ([int][char]$character - [int][char]'A' + 1)
    }
    return $value
}

function Ensure-DirectTableDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $TableSpec,
        [ValidateSet('create', 'update', 'set')]
        [string]$Mode = 'set'
    )

    $tableName = [string]$TableSpec.name
    if ([string]::IsNullOrWhiteSpace($tableName)) {
        throw "Table spec requires a name."
    }
    $sheetName = [string]$TableSpec.sheet
    if ([string]::IsNullOrWhiteSpace($sheetName)) {
        throw "Table spec requires a sheet."
    }
    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sheetName
    $topLeft = if ($null -ne $TableSpec.PSObject.Properties['topLeft']) { [string]$TableSpec.topLeft } else { $null }
    $address = if ($null -ne $TableSpec.PSObject.Properties['address']) { [string]$TableSpec.address } else { $null }

    $headerValues = if ($null -ne $TableSpec.PSObject.Properties['headers']) {
        [object[]]@($TableSpec.headers | ForEach-Object { [string]$_ })
    }
    else {
        @()
    }
    $hasRows = $null -ne $TableSpec.PSObject.Properties['rows']
    $rows = if ($hasRows) { @($TableSpec.rows) } else { @() }

    $allRows = $null
    if (@($headerValues).Count -gt 0) {
        if (@($rows).Count -lt 1) {
            $rows = ,(@("") * @($headerValues).Count)
        }

        $allRows = New-Object System.Collections.Generic.List[object[]]
        $allRows.Add($headerValues)
        foreach ($row in $rows) {
            $allRows.Add([object[]]@($row | ForEach-Object { $_ }))
        }
    }

    $existing = Find-ListObjectByName -Worksheet $worksheet -TableName $tableName
    if ($Mode -eq 'create' -and $null -ne $existing) {
        throw "Table already exists: $tableName"
    }
    if ($Mode -eq 'update' -and $null -eq $existing) {
        throw "Table not found: $tableName"
    }

    if ($null -eq $existing) {
        if (-not [string]::IsNullOrWhiteSpace($address) -and $null -eq $allRows) {
            $listObject = $worksheet.ListObjects.Add(1, $worksheet.Range($address), $null, 1)
            $listObject.Name = $tableName
            if ($null -ne $TableSpec.PSObject.Properties['styleName'] -and -not [string]::IsNullOrWhiteSpace([string]$TableSpec.styleName)) {
                try { $listObject.TableStyle = [string]$TableSpec.styleName } catch {}
            }
            return
        }

        if ([string]::IsNullOrWhiteSpace($topLeft)) {
            throw "Table spec requires topLeft or address."
        }
        if ($null -eq $allRows) {
            throw "Table spec requires headers when creating from topLeft."
        }

        $start = Get-RangeFromAddress -Worksheet $worksheet -Address $topLeft
        [void](Set-RangeValues -Range $start -Values $allRows)
        $targetRange = $start.Resize(@($allRows).Count, @($headerValues).Count)
        $listObject = $worksheet.ListObjects.Add(1, $targetRange, $null, 1)
        $listObject.Name = $tableName
        if ($null -ne $TableSpec.PSObject.Properties['styleName'] -and -not [string]::IsNullOrWhiteSpace([string]$TableSpec.styleName)) {
            try { $listObject.TableStyle = [string]$TableSpec.styleName } catch {}
        }
        return
    }

    if ((-not $hasRows) -and @($headerValues).Count -gt 0) {
        for ($col = 1; $col -le @($headerValues).Count; $col++) {
            $existing.ListColumns.Item($col).Name = [string]$headerValues[$col - 1]
        }
        if ($null -ne $TableSpec.PSObject.Properties['styleName'] -and -not [string]::IsNullOrWhiteSpace([string]$TableSpec.styleName)) {
            try { $existing.TableStyle = [string]$TableSpec.styleName } catch {}
        }
        return
    }

    if ($null -eq $allRows) {
        if (-not [string]::IsNullOrWhiteSpace($address)) {
            $existing.Resize($worksheet.Range($address))
            if ($null -ne $TableSpec.PSObject.Properties['styleName'] -and -not [string]::IsNullOrWhiteSpace([string]$TableSpec.styleName)) {
                try { $existing.TableStyle = [string]$TableSpec.styleName } catch {}
            }
            return
        }
        throw "Table spec requires headers or address for updates."
    }
    if ([string]::IsNullOrWhiteSpace($topLeft)) {
        try {
            $topLeft = $existing.Range.Cells.Item(1, 1).Address($false, $false)
        }
        catch {
            throw "Table spec requires topLeft or address for updates."
        }
    }

    $start = $worksheet.Range($topLeft)
    $targetRange = $start.Resize(@($allRows).Count, @($headerValues).Count)
    $existing.Resize($targetRange)
    for ($col = 1; $col -le @($headerValues).Count; $col++) {
        $existing.ListColumns.Item($col).Name = [string]$headerValues[$col - 1]
    }

    $bodyRows = @($allRows | Select-Object -Skip 1)
    if (@($bodyRows).Count -gt 0) {
        [void](Set-RangeValues -Range $start.Offset(1, 0) -Values $bodyRows)
    }
    if ($null -ne $TableSpec.PSObject.Properties['styleName'] -and -not [string]::IsNullOrWhiteSpace([string]$TableSpec.styleName)) {
        try { $existing.TableStyle = [string]$TableSpec.styleName } catch {}
    }
}

function Remove-DirectTableDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$TableName
    )

    foreach ($worksheet in $Workbook.Worksheets) {
        $listObject = Find-ListObjectByName -Worksheet $worksheet -TableName $TableName
        if ($null -ne $listObject) {
            $listObject.Delete()
            return $true
        }
    }

    return $false
}

function Find-WorkbookListObjectByName {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$TableName
    )

    foreach ($worksheet in $Workbook.Worksheets) {
        $listObject = Find-ListObjectByName -Worksheet $worksheet -TableName $TableName
        if ($null -ne $listObject) {
            return $listObject
        }
    }

    return $null
}

function Resolve-ChartTypeValue {
    param($ChartType)

    if ($null -eq $ChartType) {
        return $null
    }

    $raw = [string]$ChartType
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    if ($raw -match '^-?\d+$') {
        return [int]$raw
    }

    $normalized = $raw.Trim().ToLowerInvariant()
    $map = @{
        'column-clustered' = 51
        'column-stacked' = 52
        'bar-clustered' = 57
        'line' = 4
        'pie' = 5
        'area' = 1
        'scatter' = -4169
        'doughnut' = -4120
    }
    if ($map.ContainsKey($normalized)) {
        return [int]$map[$normalized]
    }

    throw "Unsupported chartType: $raw"
}

function Resolve-PivotSummaryFunctionValue {
    param($Summary)

    if ($null -eq $Summary) {
        return $null
    }

    $raw = [string]$Summary
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    if ($raw -match '^-?\d+$') {
        return [int]$raw
    }

    $normalized = $raw.Trim().ToLowerInvariant()
    $map = @{
        'sum' = -4157
        'count' = -4112
        'average' = -4106
        'max' = -4136
        'min' = -4139
    }
    if ($map.ContainsKey($normalized)) {
        return [int]$map[$normalized]
    }

    throw "Unsupported pivot summary function: $raw"
}

function Get-ChartSourceRange {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $ChartSpec
    )

    if ($null -ne $ChartSpec.PSObject.Properties['sourceTable'] -and -not [string]::IsNullOrWhiteSpace([string]$ChartSpec.sourceTable)) {
        $listObject = Find-WorkbookListObjectByName -Workbook $Workbook -TableName ([string]$ChartSpec.sourceTable)
        if ($null -eq $listObject) {
            throw "Chart source table not found: $($ChartSpec.sourceTable)"
        }
        return $listObject.Range
    }

    $sourceSheetName = if ($null -ne $ChartSpec.PSObject.Properties['sourceSheet'] -and -not [string]::IsNullOrWhiteSpace([string]$ChartSpec.sourceSheet)) {
        [string]$ChartSpec.sourceSheet
    }
    elseif ($null -ne $ChartSpec.PSObject.Properties['sheet'] -and -not [string]::IsNullOrWhiteSpace([string]$ChartSpec.sheet)) {
        [string]$ChartSpec.sheet
    }
    else {
        throw "Chart spec requires sourceSheet when sourceTable is omitted."
    }

    $sourceAddress = if ($null -ne $ChartSpec.PSObject.Properties['sourceAddress']) {
        [string]$ChartSpec.sourceAddress
    } elseif ($null -ne $ChartSpec.PSObject.Properties['sourceRange']) {
        [string]$ChartSpec.sourceRange
    } else {
        $null
    }
    if ([string]::IsNullOrWhiteSpace($sourceAddress)) {
        throw "Chart spec requires sourceAddress or sourceRange when sourceTable is omitted."
    }

    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sourceSheetName
    return $worksheet.Range($sourceAddress)
}

function Set-ChartSeriesFromRange {
    param(
        [Parameter(Mandatory = $true)]
        $Chart,
        [Parameter(Mandatory = $true)]
        $SourceRange
    )

    $rowCount = [int]$SourceRange.Rows.Count
    $colCount = [int]$SourceRange.Columns.Count
    if ($rowCount -lt 2 -or $colCount -lt 2) {
        throw "Chart source range must include a header row plus at least one category and one value column."
    }

    try {
        while ([int]$Chart.SeriesCollection().Count -gt 0) {
            $Chart.SeriesCollection(1).Delete()
        }
    }
    catch {
    }

    $sheetName = [string]$SourceRange.Worksheet.Name
    $escapedSheetName = $sheetName.Replace("'", "''")
    $startRow = [int]$SourceRange.Row
    $startColumn = [int]$SourceRange.Column
    $endRow = $startRow + $rowCount - 1
    $categoryColumnLetters = Convert-ColumnNumberToLetters -ColumnNumber $startColumn
    $categoryRef = "='" + $escapedSheetName + "'!$" + $categoryColumnLetters + "$" + ($startRow + 1) + ":$" + $categoryColumnLetters + "$" + $endRow
    for ($columnIndex = 2; $columnIndex -le $colCount; $columnIndex++) {
        $series = $Chart.SeriesCollection().NewSeries()
        try { $series.Name = [string]$SourceRange.Cells.Item(1, $columnIndex).Value2 } catch {}
        $valueColumnLetters = Convert-ColumnNumberToLetters -ColumnNumber ($startColumn + $columnIndex - 1)
        $valueRef = "='{0}'!${1}${2}:${1}${3}" -f $escapedSheetName, $valueColumnLetters, ($startRow + 1), $endRow
        $series.Values = $valueRef
        $series.XValues = $categoryRef
    }
}

function Set-ChartSeriesFromAddressSpec {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Chart,
        [Parameter(Mandatory = $true)]
        $ChartSpec
    )

    $sheetName = if ($null -ne $ChartSpec.PSObject.Properties['sourceSheet'] -and -not [string]::IsNullOrWhiteSpace([string]$ChartSpec.sourceSheet)) {
        [string]$ChartSpec.sourceSheet
    } elseif ($null -ne $ChartSpec.PSObject.Properties['sheet'] -and -not [string]::IsNullOrWhiteSpace([string]$ChartSpec.sheet)) {
        [string]$ChartSpec.sheet
    } else {
        throw "Chart spec requires sourceSheet or sheet."
    }
    $address = if ($null -ne $ChartSpec.PSObject.Properties['sourceAddress']) {
        [string]$ChartSpec.sourceAddress
    } elseif ($null -ne $ChartSpec.PSObject.Properties['sourceRange']) {
        [string]$ChartSpec.sourceRange
    } else {
        throw "Chart spec requires sourceAddress or sourceRange."
    }

    if ($address -notmatch '^\$?([A-Za-z]+)\$?(\d+):\$?([A-Za-z]+)\$?(\d+)$') {
        throw "Chart sourceAddress must be a rectangular A1 range."
    }

    $startColumn = Convert-ColumnLettersToNumber -Letters $Matches[1]
    $startRow = [int]$Matches[2]
    $endColumn = Convert-ColumnLettersToNumber -Letters $Matches[3]
    $endRow = [int]$Matches[4]
    if ($endColumn -le $startColumn -or $endRow -le $startRow) {
        throw "Chart sourceAddress must include a header row plus at least one category and one value column."
    }

    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sheetName
    $escapedSheetName = $sheetName.Replace("'", "''")
    $categoryColumnLetters = Convert-ColumnNumberToLetters -ColumnNumber $startColumn
    $categoryRef = "='" + $escapedSheetName + "'!$" + $categoryColumnLetters + "$" + ($startRow + 1) + ":$" + $categoryColumnLetters + "$" + $endRow

    try {
        while ([int]$Chart.SeriesCollection().Count -gt 0) {
            $Chart.SeriesCollection(1).Delete()
        }
    }
    catch {
    }

    for ($columnNumber = $startColumn + 1; $columnNumber -le $endColumn; $columnNumber++) {
        $series = $Chart.SeriesCollection().NewSeries()
        try { $series.Name = [string]$worksheet.Cells.Item($startRow, $columnNumber).Value2 } catch {}
        $valueColumnLetters = Convert-ColumnNumberToLetters -ColumnNumber $columnNumber
        $series.Values = "='" + $escapedSheetName + "'!$" + $valueColumnLetters + "$" + ($startRow + 1) + ":$" + $valueColumnLetters + "$" + $endRow
        $series.XValues = $categoryRef
    }
}

function Find-DirectChartDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ChartName
    )

    foreach ($worksheet in $Workbook.Worksheets) {
        $chartObjects = $null
        try { $chartObjects = $worksheet.ChartObjects() } catch { $chartObjects = $null }
        if ($null -eq $chartObjects) {
            continue
        }
        foreach ($chartObject in $chartObjects) {
            try {
                if ([string]$chartObject.Name -eq $ChartName) {
                    return [pscustomobject]@{
                        kind = 'embedded'
                        worksheet = $worksheet
                        chartObject = $chartObject
                        chart = $chartObject.Chart
                    }
                }
            }
            catch {
            }
        }
    }

    try {
        foreach ($chartSheet in $Workbook.Charts) {
            try {
                if ([string]$chartSheet.Name -eq $ChartName) {
                    return [pscustomobject]@{
                        kind = 'chart-sheet'
                        worksheet = $null
                        chartObject = $null
                        chart = $chartSheet
                    }
                }
            }
            catch {
            }
        }
    }
    catch {
    }

    return $null
}

function Set-DirectChartProperties {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Chart,
        [Parameter(Mandatory = $true)]
        $ChartSpec
    )

    if ($null -ne $ChartSpec.PSObject.Properties['sourceAddress'] -or $null -ne $ChartSpec.PSObject.Properties['sourceRange']) {
        Set-ChartSeriesFromAddressSpec -Workbook $Workbook -Chart $Chart -ChartSpec $ChartSpec
    }
    else {
        $sourceRange = Get-ChartSourceRange -Workbook $Workbook -ChartSpec $ChartSpec
        Set-ChartSeriesFromRange -Chart $Chart -SourceRange $sourceRange
    }

    $chartType = Resolve-ChartTypeValue -ChartType $ChartSpec.chartType
    if ($null -ne $chartType) {
        $Chart.ChartType = $chartType
    }

    if ($null -ne $ChartSpec.PSObject.Properties['title']) {
        if ([string]::IsNullOrWhiteSpace([string]$ChartSpec.title)) {
            $Chart.HasTitle = $false
        }
        else {
            $Chart.HasTitle = $true
            $Chart.ChartTitle.Text = [string]$ChartSpec.title
        }
    }
}

function Ensure-DirectChartDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $ChartSpec,
        [ValidateSet('create', 'update', 'set')]
        [string]$Mode = 'set'
    )

    $chartName = [string]$ChartSpec.name
    if ([string]::IsNullOrWhiteSpace($chartName)) {
        throw "Chart spec requires a name."
    }
    $sheetName = [string]$ChartSpec.sheet
    if ([string]::IsNullOrWhiteSpace($sheetName)) {
        throw "Chart spec requires a sheet."
    }

    $existing = Find-DirectChartDefinition -Workbook $Workbook -ChartName $chartName
    if ($Mode -eq 'create' -and $null -ne $existing) {
        throw "Chart already exists: $chartName"
    }
    if ($Mode -eq 'update' -and $null -eq $existing) {
        throw "Chart not found: $chartName"
    }

    if ($null -eq $existing) {
        $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sheetName
        $topLeft = if ($null -ne $ChartSpec.PSObject.Properties['topLeft'] -and -not [string]::IsNullOrWhiteSpace([string]$ChartSpec.topLeft)) {
            [string]$ChartSpec.topLeft
        } else {
            'H2'
        }
        $anchor = $worksheet.Range($topLeft)
        $width = if ($null -ne $ChartSpec.PSObject.Properties['width'] -and $null -ne $ChartSpec.width) { [double]$ChartSpec.width } else { 480 }
        $height = if ($null -ne $ChartSpec.PSObject.Properties['height'] -and $null -ne $ChartSpec.height) { [double]$ChartSpec.height } else { 288 }
        $chartObject = $worksheet.ChartObjects().Add([double]$anchor.Left, [double]$anchor.Top, $width, $height)
        $chartObject.Name = $chartName
        [void](Set-DirectChartProperties -Workbook $Workbook -Chart $chartObject.Chart -ChartSpec $ChartSpec)
        return
    }

    if ($existing.kind -ne 'embedded' -and [string]$existing.chart.Name -ne $sheetName) {
        throw "Chart update currently supports embedded charts or chart-sheet updates on the same sheet name."
    }

    [void](Set-DirectChartProperties -Workbook $Workbook -Chart $existing.chart -ChartSpec $ChartSpec)
    return
}

function Remove-DirectChartDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ChartName
    )

    $existing = Find-DirectChartDefinition -Workbook $Workbook -ChartName $ChartName
    if ($null -eq $existing) {
        return $false
    }

    if ($existing.kind -eq 'embedded') {
        $existing.chartObject.Delete()
        return $true
    }

    $existing.chart.Delete()
    return $true
}

function Find-DirectPivotDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$PivotName
    )

    foreach ($worksheet in $Workbook.Worksheets) {
        $pivotTables = $null
        try { $pivotTables = $worksheet.PivotTables() } catch { $pivotTables = $null }
        if ($null -eq $pivotTables) {
            continue
        }
        foreach ($pivotTable in $pivotTables) {
            try {
                if ([string]$pivotTable.Name -eq $PivotName) {
                    return [pscustomobject]@{
                        worksheet = $worksheet
                        pivotTable = $pivotTable
                    }
                }
            }
            catch {
            }
        }
    }

    return $null
}

function Remove-DirectPivotDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$PivotName
    )

    $existing = Find-DirectPivotDefinition -Workbook $Workbook -PivotName $PivotName
    if ($null -eq $existing) {
        return $false
    }

    try {
        $existing.pivotTable.TableRange2.Clear()
    }
    catch {
        try {
            $existing.pivotTable.TableRange2.ClearContents()
        }
        catch {
        }
    }
    return $true
}

function Get-PivotSourceDataReference {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $PivotSpec
    )

    if ($null -ne $PivotSpec.PSObject.Properties['sourceTable'] -and -not [string]::IsNullOrWhiteSpace([string]$PivotSpec.sourceTable)) {
        $listObject = Find-WorkbookListObjectByName -Workbook $Workbook -TableName ([string]$PivotSpec.sourceTable)
        if ($null -eq $listObject) {
            throw "Pivot source table not found: $($PivotSpec.sourceTable)"
        }
        return [string]$listObject.Name
    }

    $sourceSheetName = if ($null -ne $PivotSpec.PSObject.Properties['sourceSheet'] -and -not [string]::IsNullOrWhiteSpace([string]$PivotSpec.sourceSheet)) {
        [string]$PivotSpec.sourceSheet
    } else {
        throw "Pivot spec requires sourceSheet when sourceTable is omitted."
    }
    $sourceAddress = if ($null -ne $PivotSpec.PSObject.Properties['sourceAddress']) {
        [string]$PivotSpec.sourceAddress
    } elseif ($null -ne $PivotSpec.PSObject.Properties['sourceRange']) {
        [string]$PivotSpec.sourceRange
    } else {
        $null
    }
    if ([string]::IsNullOrWhiteSpace($sourceAddress)) {
        throw "Pivot spec requires sourceAddress or sourceRange when sourceTable is omitted."
    }

    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sourceSheetName
    $range = $worksheet.Range($sourceAddress)
    return [string]$range.Address($true, $true, 1, $true)
}

function Set-PivotFieldOrientation {
    param(
        [Parameter(Mandatory = $true)]
        $PivotTable,
        [Parameter(Mandatory = $true)]
        [string]$FieldName,
        [Parameter(Mandatory = $true)]
        [int]$Orientation,
        [Parameter(Mandatory = $true)]
        [int]$Position
    )

    $field = $PivotTable.PivotFields($FieldName)
    $field.Orientation = $Orientation
    if ($Orientation -ne 4) {
        $field.Position = $Position
    }
    return $field
}

function Configure-DirectPivotDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $PivotTable,
        [Parameter(Mandatory = $true)]
        $PivotSpec
    )

    $rowFields = if ($null -ne $PivotSpec.PSObject.Properties['rowFields']) { @($PivotSpec.rowFields) } else { @() }
    $columnFields = if ($null -ne $PivotSpec.PSObject.Properties['columnFields']) { @($PivotSpec.columnFields) } else { @() }
    $pageFields = if ($null -ne $PivotSpec.PSObject.Properties['pageFields']) { @($PivotSpec.pageFields) } else { @() }
    $dataFields = if ($null -ne $PivotSpec.PSObject.Properties['dataFields']) { @($PivotSpec.dataFields) } else { @() }

    $position = 1
    foreach ($fieldName in $rowFields) {
        [void](Set-PivotFieldOrientation -PivotTable $PivotTable -FieldName ([string]$fieldName) -Orientation 1 -Position $position)
        $position += 1
    }

    $position = 1
    foreach ($fieldName in $columnFields) {
        [void](Set-PivotFieldOrientation -PivotTable $PivotTable -FieldName ([string]$fieldName) -Orientation 2 -Position $position)
        $position += 1
    }

    $position = 1
    foreach ($fieldName in $pageFields) {
        [void](Set-PivotFieldOrientation -PivotTable $PivotTable -FieldName ([string]$fieldName) -Orientation 3 -Position $position)
        $position += 1
    }

    foreach ($fieldSpec in $dataFields) {
        $fieldName = if ($fieldSpec -is [string]) { [string]$fieldSpec } else { [string]$fieldSpec.name }
        if ([string]::IsNullOrWhiteSpace($fieldName)) {
            continue
        }
        $baseField = $PivotTable.PivotFields($fieldName)
        $summary = if ($fieldSpec -is [string]) { $null } else { Resolve-PivotSummaryFunctionValue -Summary $fieldSpec.summary }
        $caption = if ($fieldSpec -is [string] -or $null -eq $fieldSpec.PSObject.Properties['caption']) { $null } else { [string]$fieldSpec.caption }
        if ($null -ne $summary -and -not [string]::IsNullOrWhiteSpace($caption)) {
            $dataField = $PivotTable.AddDataField($baseField, $caption, $summary)
        }
        elseif ($null -ne $summary) {
            $dataField = $PivotTable.AddDataField($baseField, ("{0} of {1}" -f (([string]$fieldSpec.summary).Trim()), $fieldName), $summary)
        }
        else {
            $dataField = $PivotTable.AddDataField($baseField)
        }
        if ($null -ne $fieldSpec.PSObject.Properties['numberFormat'] -and -not [string]::IsNullOrWhiteSpace([string]$fieldSpec.numberFormat)) {
            try { $dataField.NumberFormat = [string]$fieldSpec.numberFormat } catch {}
        }
    }
}

function Ensure-DirectPivotDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $PivotSpec,
        [ValidateSet('create', 'update', 'set')]
        [string]$Mode = 'set'
    )

    $pivotName = [string]$PivotSpec.name
    if ([string]::IsNullOrWhiteSpace($pivotName)) {
        throw "Pivot spec requires a name."
    }
    $destinationSheetName = if ($null -ne $PivotSpec.PSObject.Properties['destinationSheet'] -and -not [string]::IsNullOrWhiteSpace([string]$PivotSpec.destinationSheet)) {
        [string]$PivotSpec.destinationSheet
    } elseif ($null -ne $PivotSpec.PSObject.Properties['sheet'] -and -not [string]::IsNullOrWhiteSpace([string]$PivotSpec.sheet)) {
        [string]$PivotSpec.sheet
    } else {
        throw "Pivot spec requires destinationSheet or sheet."
    }
    $topLeft = if ($null -ne $PivotSpec.PSObject.Properties['topLeft']) { [string]$PivotSpec.topLeft } else { $null }
    if ([string]::IsNullOrWhiteSpace($topLeft)) {
        throw "Pivot spec requires topLeft."
    }

    $existing = Find-DirectPivotDefinition -Workbook $Workbook -PivotName $pivotName
    if ($Mode -eq 'create' -and $null -ne $existing) {
        throw "Pivot already exists: $pivotName"
    }
    if ($Mode -eq 'update' -and $null -eq $existing) {
        throw "Pivot not found: $pivotName"
    }
    if ($null -ne $existing) {
        [void](Remove-DirectPivotDefinition -Workbook $Workbook -PivotName $pivotName)
    }

    $destinationWorksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $destinationSheetName
    $destinationRange = $destinationWorksheet.Range($topLeft)
    $sourceData = Get-PivotSourceDataReference -Workbook $Workbook -PivotSpec $PivotSpec
    $pivotCache = $Workbook.PivotCaches().Create(1, $sourceData)
    $pivotCache.CreatePivotTable($destinationRange, $pivotName) | Out-Null
    $pivotTable = $destinationWorksheet.PivotTables($pivotName)
    Configure-DirectPivotDefinition -PivotTable $pivotTable -PivotSpec $PivotSpec
}

function Get-SlicerCacheTypeValue {
    param($SlicerCache)

    try {
        return [int](Get-LateProperty -Target $SlicerCache -Name 'SlicerCacheType')
    }
    catch {
        return $null
    }
}

function Test-IsTimelineSlicerCache {
    param($SlicerCache)

    $cacheType = Get-SlicerCacheTypeValue -SlicerCache $SlicerCache
    if ($cacheType -eq 2) {
        return $true
    }

    try {
        $null = Get-LateProperty -Target $SlicerCache -Name 'TimelineState'
        return $true
    }
    catch {
        return $false
    }
}

function Get-SlicerCacheFieldName {
    param($SlicerCache)

    foreach ($propertyName in @('SourceNameStandard', 'SourceName', 'Name')) {
        try {
            $value = [string](Get-LateProperty -Target $SlicerCache -Name $propertyName)
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                return $value
            }
        }
        catch {
        }
    }

    return $null
}

function Get-SlicerCachePivotTableNames {
    param($SlicerCache)

    $names = @()
    try {
        foreach ($pivotTable in (Get-LateProperty -Target $SlicerCache -Name 'PivotTables')) {
            try {
                $names += [string]$pivotTable.Name
            }
            catch {
            }
        }
    }
    catch {
    }

    return @($names | Sort-Object -Unique)
}

function Get-SlicerVisibleItemsList {
    param($SlicerCache)

    $fallbackSelections = @()
    try {
        $selectedNames = New-Object System.Collections.Generic.List[string]
        $allSelected = $true
        $itemCount = 0
        foreach ($item in @($SlicerCache.SlicerItems())) {
            $itemCount++
            $selected = $false
            try { $selected = [bool]$item.Selected } catch { $selected = $false }
            if (-not $selected) {
                $allSelected = $false
                continue
            }
            $name = $null
            try { $name = [string]$item.Name } catch {}
            if ([string]::IsNullOrWhiteSpace($name)) {
                try { $name = [string]$item.Caption } catch {}
            }
            if (-not [string]::IsNullOrWhiteSpace($name)) {
                $selectedNames.Add($name) | Out-Null
            }
        }
        if ($itemCount -gt 0 -and -not $allSelected) {
            $fallbackSelections = @($selectedNames.ToArray())
        }
    }
    catch {
    }

    try {
        $visibleItems = @((Get-LateProperty -Target $SlicerCache -Name 'VisibleSlicerItemsList'))
        if (@($visibleItems).Count -gt 0) {
            return $visibleItems
        }
    }
    catch {
    }

    return $fallbackSelections
}

function Get-TimelineStatePayload {
    param($SlicerCache)

    $state = $null
    try { $state = Get-LateProperty -Target $SlicerCache -Name 'TimelineState' } catch { $state = $null }
    if ($null -eq $state) {
        return $null
    }

    $payload = [ordered]@{
        startDate = $null
        endDate = $null
        filterType = $null
        filterValue1 = $null
        filterValue2 = $null
    }
    foreach ($propertyName in @('StartDate', 'EndDate', 'FilterType', 'FilterValue1', 'FilterValue2')) {
        try {
            $value = Get-LateProperty -Target $state -Name $propertyName
            switch ($propertyName) {
                'StartDate' { $payload.startDate = $value }
                'EndDate' { $payload.endDate = $value }
                'FilterType' { $payload.filterType = $value }
                'FilterValue1' { $payload.filterValue1 = $value }
                'FilterValue2' { $payload.filterValue2 = $value }
            }
        }
        catch {
        }
    }

    return [pscustomobject]$payload
}

function Get-SlicerSourceTypeName {
    param($SlicerCache)

    try {
        if ([bool](Get-LateProperty -Target $SlicerCache -Name 'OLAP')) {
            return 'olap'
        }
    }
    catch {
    }

    if (@(Get-SlicerCachePivotTableNames -SlicerCache $SlicerCache).Count -gt 0) {
        return 'pivot'
    }

    try {
        $workbookConnection = Get-LateProperty -Target $SlicerCache -Name 'WorkbookConnection'
        if ($null -ne $workbookConnection) {
            return 'connection'
        }
    }
    catch {
    }

    return 'unknown'
}

function Get-SlicerEntryPayload {
    param(
        [Parameter(Mandatory = $true)]
        $Slicer,
        [Parameter(Mandatory = $true)]
        $SlicerCache,
        [switch]$Timeline
    )

    $entry = [ordered]@{
        name = $null
        cacheName = $null
        sheet = $null
        caption = $null
        sourceField = $null
        sourceType = $null
        olap = $null
        cacheType = if ($Timeline) { 'timeline' } else { 'slicer' }
        pivotTables = @()
        style = $null
        topLeft = $null
        width = $null
        height = $null
        address = $null
        displayHeader = $null
        numberOfColumns = $null
        locked = $null
        disableMoveResizeUI = $null
        altText = $null
    }

    try { $entry.name = [string]$Slicer.Name } catch {}
    try { $entry.cacheName = [string]$SlicerCache.Name } catch {}
    try { $entry.sheet = [string]$Slicer.Shape.Parent.Name } catch {}
    try { $entry.caption = [string]$Slicer.Caption } catch {}
    try { $entry.sourceField = Get-SlicerCacheFieldName -SlicerCache $SlicerCache } catch {}
    try { $entry.sourceType = Get-SlicerSourceTypeName -SlicerCache $SlicerCache } catch {}
    try { $entry.olap = [bool](Get-LateProperty -Target $SlicerCache -Name 'OLAP') } catch {}
    try { $entry.pivotTables = @(Get-SlicerCachePivotTableNames -SlicerCache $SlicerCache) } catch {}
    try { $entry.style = [string]$Slicer.Style } catch {}
    try { $entry.topLeft = [string]$Slicer.TopLeftCell.Address($false, $false) } catch {}
    try { $entry.width = [double]$Slicer.Shape.Width } catch {}
    try { $entry.height = [double]$Slicer.Shape.Height } catch {}
    try {
        $topLeft = $Slicer.TopLeftCell.Address($false, $false)
        $bottomRight = $Slicer.BottomRightCell.Address($false, $false)
        $entry.address = "{0}:{1}" -f $topLeft, $bottomRight
    } catch {}
    try { $entry.displayHeader = [bool]$Slicer.DisplayHeader } catch {}
    try { $entry.numberOfColumns = [int]$Slicer.NumberOfColumns } catch {}
    try { $entry.locked = [bool]$Slicer.Shape.Locked } catch {}
    try { $entry.disableMoveResizeUI = [bool]$Slicer.DisableMoveResizeUI } catch {}
    try { $entry.altText = [string]$Slicer.Shape.AlternativeText } catch {}

    if ($Timeline) {
        $timelineState = Get-TimelineStatePayload -SlicerCache $SlicerCache
        if ($null -ne $timelineState) {
            $entry['timelineState'] = $timelineState
            $entry['startDate'] = $timelineState.startDate
            $entry['endDate'] = $timelineState.endDate
            $entry['filterType'] = $timelineState.filterType
            $entry['filterValue1'] = $timelineState.filterValue1
            $entry['filterValue2'] = $timelineState.filterValue2
        }
        foreach ($propertyName in @('TimelineViewState', 'TimelineState')) {
            try {
                $viewState = Get-LateProperty -Target $Slicer -Name $propertyName
                if ($null -ne $viewState) {
                    try { $entry['timelineLevel'] = Get-LateProperty -Target $viewState -Name 'Level' } catch {}
                    if ($null -ne $entry['timelineLevel']) {
                        break
                    }
                }
            }
            catch {
            }
        }
    }
    else {
        $entry['visibleItemsList'] = @(Get-SlicerVisibleItemsList -SlicerCache $SlicerCache)
    }

    return [pscustomobject]$entry
}

function Get-SlicerQuery {
    param($Workbook)

    $items = @()
    try {
        foreach ($slicerCache in $Workbook.SlicerCaches()) {
            if (Test-IsTimelineSlicerCache -SlicerCache $slicerCache) {
                continue
            }
            foreach ($slicer in (Get-LateProperty -Target $slicerCache -Name 'Slicers')) {
                $items += Get-SlicerEntryPayload -Slicer $slicer -SlicerCache $slicerCache
            }
        }
    }
    catch {
    }

    return @($items | Sort-Object sheet, name)
}

function Get-TimelineQuery {
    param($Workbook)

    $items = @()
    try {
        foreach ($slicerCache in $Workbook.SlicerCaches()) {
            if (-not (Test-IsTimelineSlicerCache -SlicerCache $slicerCache)) {
                continue
            }
            foreach ($timeline in (Get-LateProperty -Target $slicerCache -Name 'Slicers')) {
                $items += Get-SlicerEntryPayload -Slicer $timeline -SlicerCache $slicerCache -Timeline
            }
        }
    }
    catch {
    }

    return @($items | Sort-Object sheet, name)
}

function Find-DirectSlicerControlDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [switch]$Timeline
    )

    try {
        foreach ($slicerCache in $Workbook.SlicerCaches()) {
            $isTimeline = Test-IsTimelineSlicerCache -SlicerCache $slicerCache
            if ($Timeline -and -not $isTimeline) {
                continue
            }
            if (-not $Timeline -and $isTimeline) {
                continue
            }
            foreach ($slicer in (Get-LateProperty -Target $slicerCache -Name 'Slicers')) {
                try {
                    if ([string]$slicer.Name -eq $Name) {
                        return [pscustomobject]@{
                            cache = $slicerCache
                            slicer = $slicer
                            timeline = $isTimeline
                        }
                    }
                }
                catch {
                }
            }
        }
    }
    catch {
    }

    return $null
}

function Find-WorkbookSlicerCacheByName {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$CacheName
    )

    try {
        foreach ($slicerCache in $Workbook.SlicerCaches()) {
            try {
                if ([string]$slicerCache.Name -eq $CacheName) {
                    return $slicerCache
                }
            }
            catch {
            }
        }
    }
    catch {
    }

    return $null
}

function Resolve-TimelineLevelValue {
    param($Level)

    if ($null -eq $Level) {
        return $null
    }
    if ($Level -is [int]) {
        return [int]$Level
    }

    switch (([string]$Level).Trim().ToLowerInvariant()) {
        'days' { return 0 }
        'months' { return 1 }
        'quarters' { return 2 }
        'years' { return 3 }
        default { return $null }
    }
}

function Resolve-SlicerCacheSourceObject {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Spec
    )

    if ($null -ne $Spec.PSObject.Properties['sourcePivot'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.sourcePivot)) {
        $pivotDefinition = Find-DirectPivotDefinition -Workbook $Workbook -PivotName ([string]$Spec.sourcePivot)
        if ($null -eq $pivotDefinition) {
            throw "Pivot not found for slicer/timeline source: $($Spec.sourcePivot)"
        }
        return $pivotDefinition.pivotTable
    }

    if ($null -ne $Spec.PSObject.Properties['sourceConnection'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.sourceConnection)) {
        try {
            return $Workbook.Connections.Item([string]$Spec.sourceConnection)
        }
        catch {
            throw "Connection not found for slicer/timeline source: $($Spec.sourceConnection)"
        }
    }

    throw "Slicer/timeline spec requires sourcePivot or sourceConnection unless cacheName reuses an existing cache."
}

function New-WorkbookSlicerCache {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Spec,
        [switch]$Timeline
    )

    $sourceField = if ($null -ne $Spec.PSObject.Properties['sourceField']) { [string]$Spec.sourceField } else { $null }
    if ([string]::IsNullOrWhiteSpace($sourceField)) {
        throw "Slicer/timeline spec requires sourceField when creating a new cache."
    }
    $cacheName = if ($null -ne $Spec.PSObject.Properties['cacheName'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.cacheName)) {
        [string]$Spec.cacheName
    }
    elseif ($null -ne $Spec.PSObject.Properties['name'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.name)) {
        [string]$Spec.name
    }
    else {
        $null
    }
    $sourceObject = Resolve-SlicerCacheSourceObject -Workbook $Workbook -Spec $Spec

    $attempts = @()
    if ($Timeline) {
        $attempts += @(
            { $Workbook.SlicerCaches().Add2($sourceObject, $sourceField, $cacheName, 2) },
            { $Workbook.SlicerCaches().Add2($sourceObject, $sourceField, $cacheName, $null, 2) },
            { $Workbook.SlicerCaches().Add2($sourceObject, $sourceField, $null, 2) }
        )
    }
    else {
        $attempts += @(
            { $Workbook.SlicerCaches().Add($sourceObject, $sourceField, $cacheName) },
            { $Workbook.SlicerCaches().Add($sourceObject, $sourceField) },
            { $Workbook.SlicerCaches().Add2($sourceObject, $sourceField, $cacheName, 1) }
        )
    }

    foreach ($attempt in $attempts) {
        try {
            $cache = & $attempt
            if ($null -ne $cache) {
                return $cache
            }
        }
        catch {
        }
    }

    throw "Failed to create slicer cache for source field '$sourceField'."
}

function Resolve-WorkbookSlicerCache {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Spec,
        [switch]$Timeline
    )

    if ($null -ne $Spec.PSObject.Properties['cacheName'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.cacheName)) {
        $existing = Find-WorkbookSlicerCacheByName -Workbook $Workbook -CacheName ([string]$Spec.cacheName)
        if ($null -ne $existing) {
            return $existing
        }
    }

    return New-WorkbookSlicerCache -Workbook $Workbook -Spec $Spec -Timeline:$Timeline
}

function Set-DirectSlicerControlProperties {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Slicer,
        [Parameter(Mandatory = $true)]
        $Spec,
        [switch]$Timeline
    )

    if ($null -ne $Spec.PSObject.Properties['caption'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.caption)) {
        try { $Slicer.Caption = [string]$Spec.caption } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['displayHeader'] -and $null -ne $Spec.displayHeader) {
        try { $Slicer.DisplayHeader = [bool]$Spec.displayHeader } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['numberOfColumns'] -and $null -ne $Spec.numberOfColumns -and -not $Timeline) {
        try { $Slicer.NumberOfColumns = [int]$Spec.numberOfColumns } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['style'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.style)) {
        try { $Slicer.Style = [string]$Spec.style } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['locked'] -and $null -ne $Spec.locked) {
        try { $Slicer.Shape.Locked = [bool]$Spec.locked } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['disableMoveResizeUI'] -and $null -ne $Spec.disableMoveResizeUI) {
        try { $Slicer.DisableMoveResizeUI = [bool]$Spec.disableMoveResizeUI } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['altText']) {
        try { $Slicer.Shape.AlternativeText = [string]$Spec.altText } catch {}
    }

    $worksheet = $null
    if ($null -ne $Spec.PSObject.Properties['sheet'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.sheet)) {
        $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName ([string]$Spec.sheet)
    }
    if ($null -ne $worksheet) {
        $topLeft = if ($null -ne $Spec.PSObject.Properties['topLeft'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.topLeft)) { [string]$Spec.topLeft } else { $null }
        if (-not [string]::IsNullOrWhiteSpace($topLeft)) {
            $anchor = $worksheet.Range($topLeft)
            try { $Slicer.Shape.Left = [double]$anchor.Left } catch {}
            try { $Slicer.Shape.Top = [double]$anchor.Top } catch {}
        }
    }
    if ($null -ne $Spec.PSObject.Properties['width'] -and $null -ne $Spec.width) {
        try { $Slicer.Shape.Width = [double]$Spec.width } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['height'] -and $null -ne $Spec.height) {
        try { $Slicer.Shape.Height = [double]$Spec.height } catch {}
    }
}

function Set-SlicerCacheFilterState {
    param(
        [Parameter(Mandatory = $true)]
        $SlicerCache,
        [Parameter(Mandatory = $true)]
        $Spec
    )

    try { Invoke-LateMethod -Target $SlicerCache -Name 'ClearManualFilter' | Out-Null } catch {}

    $visibleItems = @()
    if ($null -ne $Spec.PSObject.Properties['visibleItemsList']) {
        $visibleItems = @($Spec.visibleItemsList)
    }
    elseif ($null -ne $Spec.PSObject.Properties['visibleItems']) {
        $visibleItems = @($Spec.visibleItems)
    }

    if (@($visibleItems).Count -gt 0) {
        $selectedLookup = @{}
        foreach ($itemName in @($visibleItems)) {
            if ($null -eq $itemName) {
                continue
            }
            $selectedLookup[[string]$itemName] = $true
        }

        $appliedBySelection = $false
        try {
            $slicerItems = @($SlicerCache.SlicerItems())
            if (@($slicerItems).Count -gt 0) {
                $matchedCount = 0
                foreach ($item in $slicerItems) {
                    $itemName = $null
                    $itemCaption = $null
                    try { $itemName = [string]$item.Name } catch {}
                    try { $itemCaption = [string]$item.Caption } catch {}
                    $shouldSelect = $false
                    if (-not [string]::IsNullOrWhiteSpace($itemName) -and $selectedLookup.ContainsKey($itemName)) {
                        $shouldSelect = $true
                        $matchedCount++
                    }
                    elseif (-not [string]::IsNullOrWhiteSpace($itemCaption) -and $selectedLookup.ContainsKey($itemCaption)) {
                        $shouldSelect = $true
                        $matchedCount++
                    }
                    try { $item.Selected = $shouldSelect } catch {}
                }
                if ($matchedCount -gt 0) {
                    $appliedBySelection = $true
                }
            }
        }
        catch {
        }

        if (-not $appliedBySelection) {
            try { $SlicerCache.VisibleSlicerItemsList = @($visibleItems) } catch {}
        }
    }
}

function Set-TimelineCacheFilterState {
    param(
        [Parameter(Mandatory = $true)]
        $SlicerCache,
        [Parameter(Mandatory = $true)]
        $Spec
    )

    if ($null -eq $Spec) {
        return
    }

    $timelineState = $null
    try { $timelineState = Get-LateProperty -Target $SlicerCache -Name 'TimelineState' } catch { $timelineState = $null }
    if ($null -eq $timelineState) {
        return
    }

    if ($null -ne $Spec.PSObject.Properties['timelineLevel'] -and $null -ne $Spec.timelineLevel) {
        $levelValue = Resolve-TimelineLevelValue -Level $Spec.timelineLevel
        if ($null -ne $levelValue) {
            try { $timelineState.Level = $levelValue } catch {}
        }
    }

    $startDate = if ($null -ne $Spec.PSObject.Properties['startDate']) { $Spec.startDate } else { $null }
    $endDate = if ($null -ne $Spec.PSObject.Properties['endDate']) { $Spec.endDate } else { $null }
    if ($null -ne $startDate -and $null -ne $endDate) {
        try {
            Invoke-LateMethod -Target $timelineState -Name 'SetFilterDateRange' -Arguments @($startDate, $endDate) | Out-Null
        }
        catch {
        }
    }
}

function Ensure-DirectSlicerLikeDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Spec,
        [ValidateSet('create', 'update', 'set')]
        [string]$Mode = 'set',
        [switch]$Timeline
    )

    $name = [string]$Spec.name
    if ([string]::IsNullOrWhiteSpace($name)) {
        throw "Slicer/timeline spec requires a name."
    }
    $sheetName = if ($null -ne $Spec.PSObject.Properties['sheet']) { [string]$Spec.sheet } else { $null }
    if ([string]::IsNullOrWhiteSpace($sheetName)) {
        throw "Slicer/timeline spec requires a sheet."
    }

    $existing = Find-DirectSlicerControlDefinition -Workbook $Workbook -Name $name -Timeline:$Timeline
    if ($Mode -eq 'create' -and $null -ne $existing) {
        throw ("{0} already exists: {1}" -f ($(if ($Timeline) { 'Timeline' } else { 'Slicer' }), $name))
    }
    if ($Mode -eq 'update' -and $null -eq $existing) {
        throw ("{0} not found: {1}" -f ($(if ($Timeline) { 'Timeline' } else { 'Slicer' }), $name))
    }

    $slicerControl = $null
    $cache = $null
    if ($null -eq $existing) {
        $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sheetName
        $cache = Resolve-WorkbookSlicerCache -Workbook $Workbook -Spec $Spec -Timeline:$Timeline
        $topLeft = if ($null -ne $Spec.PSObject.Properties['topLeft'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.topLeft)) { [string]$Spec.topLeft } else { 'H2' }
        $anchor = $worksheet.Range($topLeft)
        $width = if ($null -ne $Spec.PSObject.Properties['width'] -and $null -ne $Spec.width) { [double]$Spec.width } else { 192 }
        $height = if ($null -ne $Spec.PSObject.Properties['height'] -and $null -ne $Spec.height) { [double]$Spec.height } else { $(if ($Timeline) { 72 } else { 144 }) }
        $caption = if ($null -ne $Spec.PSObject.Properties['caption'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.caption)) { [string]$Spec.caption } else { $name }
        $missing = [System.Type]::Missing

        $created = $null
        $slicerCollection = $cache.Slicers
        foreach ($attempt in @(
            { $slicerCollection.Add($worksheet, $missing, $name, $caption, [double]$anchor.Top, [double]$anchor.Left, $width, $height) },
            { $slicerCollection.Add($worksheet, $missing, $name, $caption) }
        )) {
            try {
                $created = & $attempt
                if ($null -ne $created) {
                    break
                }
            }
            catch {
            }
        }
        if ($null -eq $created) {
            throw "Failed to create slicer/timeline control '$name'."
        }
        $slicerControl = $created
    }
    else {
        $cache = $existing.cache
        $slicerControl = $existing.slicer
    }

    Set-DirectSlicerControlProperties -Workbook $Workbook -Slicer $slicerControl -Spec $Spec -Timeline:$Timeline
    if ($Timeline) {
        Set-TimelineCacheFilterState -SlicerCache $cache -Spec $Spec
    }
    else {
        Set-SlicerCacheFilterState -SlicerCache $cache -Spec $Spec
    }
}

function Remove-DirectSlicerLikeDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [switch]$Timeline
    )

    $existing = Find-DirectSlicerControlDefinition -Workbook $Workbook -Name $Name -Timeline:$Timeline
    if ($null -eq $existing) {
        return $false
    }

    $existing.slicer.Delete()
    return $true
}

function Remove-WorkbookQueryDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$QueryName
    )

    foreach ($query in $Workbook.Queries) {
        if ([string]$query.Name -ne $QueryName) {
            continue
        }

        Invoke-LateMethod -Target $query -Name 'Delete' | Out-Null
        return $true
    }

    return $false
}

function Get-DirectWorkbookQueryPayload {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook
    )

    return Get-WorkbookPowerQueryArtifacts -Workbook $Workbook
}

function Get-WorksheetShapeAnchor {
    param(
        [Parameter(Mandatory = $true)]
        $Worksheet,
        [AllowNull()]
        [string]$TopLeft,
        [AllowNull()]
        [double]$Left,
        [AllowNull()]
        [double]$Top
    )

    if (-not [string]::IsNullOrWhiteSpace($TopLeft)) {
        $range = $Worksheet.Range($TopLeft)
        return [pscustomobject]@{
            left = [double]$range.Left
            top = [double]$range.Top
        }
    }

    return [pscustomobject]@{
        left = if ($null -ne $Left) { [double]$Left } else { 0.0 }
        top = if ($null -ne $Top) { [double]$Top } else { 0.0 }
    }
}

function Get-DirectDrawingPayload {
    param(
        [Parameter(Mandatory = $true)]
        $Shape,
        [Parameter(Mandatory = $true)]
        [string]$Sheet
    )

    $entry = [ordered]@{
        name = $null
        sheet = $Sheet
        type = $null
        category = 'shape'
        left = $null
        top = $null
        width = $null
        height = $null
        topLeft = $null
        bottomRight = $null
        text = $null
        altText = $null
        visible = $null
        placement = $null
        formControlType = $null
        linkedCell = $null
        sourceName = $null
    }

    try { $entry.name = [string]$Shape.Name } catch {}
    try { $entry.type = [int]$Shape.Type } catch {}
    if ($entry.type -eq 13) {
        $entry.category = 'picture'
    }
    elseif ($entry.type -in @(8, 12)) {
        $entry.category = 'control'
    }
    try { $entry.left = [math]::Round([double]$Shape.Left, 3) } catch {}
    try { $entry.top = [math]::Round([double]$Shape.Top, 3) } catch {}
    try { $entry.width = [math]::Round([double]$Shape.Width, 3) } catch {}
    try { $entry.height = [math]::Round([double]$Shape.Height, 3) } catch {}
    try { $entry.topLeft = [string]$Shape.TopLeftCell.Address($false, $false) } catch {}
    try { $entry.bottomRight = [string]$Shape.BottomRightCell.Address($false, $false) } catch {}
    try { $entry.altText = [string]$Shape.AlternativeText } catch {}
    try { $entry.visible = [bool]$Shape.Visible } catch {}
    try { $entry.placement = [int]$Shape.Placement } catch {}
    try {
        if ($null -ne $Shape.TextFrame2 -and $Shape.TextFrame2.HasText) {
            $entry.text = [string]$Shape.TextFrame2.TextRange.Text
        }
    }
    catch {
        try { $entry.text = [string]$Shape.TextFrame.Characters().Text } catch {}
    }
    try { $entry.formControlType = [int]$Shape.FormControlType } catch {}
    try { $entry.linkedCell = [string]$Shape.ControlFormat.LinkedCell } catch {}
    try { $entry.sourceName = [string]$Shape.OnAction } catch {}

    return [pscustomobject]$entry
}

function Get-DrawingQuery {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [ValidateSet('all', 'shapes', 'pictures', 'controls')]
        [string]$Kind = 'all'
    )

    $items = @()
    foreach ($worksheet in $Workbook.Worksheets) {
        $shapes = $null
        try { $shapes = $worksheet.Shapes } catch { $shapes = $null }
        if ($null -eq $shapes) {
            continue
        }

        foreach ($shape in $shapes) {
            $entry = Get-DirectDrawingPayload -Shape $shape -Sheet ([string]$worksheet.Name)
            if ($Kind -eq 'pictures' -and $entry.category -ne 'picture') {
                continue
            }
            if ($Kind -eq 'controls' -and $entry.category -ne 'control') {
                continue
            }
            if ($Kind -eq 'shapes' -and $entry.category -ne 'shape') {
                continue
            }
            $items += $entry
        }
    }

    return @($items | Sort-Object sheet, name)
}

function Find-DirectDrawing {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [ValidateSet('all', 'shapes', 'pictures', 'controls')]
        [string]$Kind = 'all'
    )

    foreach ($worksheet in $Workbook.Worksheets) {
        $shapes = $null
        try { $shapes = $worksheet.Shapes } catch { $shapes = $null }
        if ($null -eq $shapes) {
            continue
        }
        foreach ($shape in $shapes) {
            try {
                if ([string]$shape.Name -ne $Name) {
                    continue
                }
                $payload = Get-DirectDrawingPayload -Shape $shape -Sheet ([string]$worksheet.Name)
                if ($Kind -eq 'pictures' -and $payload.category -ne 'picture') {
                    continue
                }
                if ($Kind -eq 'controls' -and $payload.category -ne 'control') {
                    continue
                }
                if ($Kind -eq 'shapes' -and $payload.category -ne 'shape') {
                    continue
                }
                return [pscustomobject]@{
                    worksheet = $worksheet
                    shape = $shape
                    payload = $payload
                }
            }
            catch {
            }
        }
    }

    return $null
}

function Set-DirectDrawingProperties {
    param(
        [Parameter(Mandatory = $true)]
        $Shape,
        [Parameter(Mandatory = $true)]
        $Spec
    )

    if ($null -ne $Spec.PSObject.Properties['text']) {
        try { $Shape.TextFrame2.TextRange.Text = [string]$Spec.text } catch { try { $Shape.TextFrame.Characters().Text = [string]$Spec.text } catch {} }
    }
    if ($null -ne $Spec.PSObject.Properties['altText']) {
        try { $Shape.AlternativeText = [string]$Spec.altText } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['width'] -and $null -ne $Spec.width) {
        try { $Shape.Width = [double]$Spec.width } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['height'] -and $null -ne $Spec.height) {
        try { $Shape.Height = [double]$Spec.height } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['left'] -and $null -ne $Spec.left) {
        try { $Shape.Left = [double]$Spec.left } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['top'] -and $null -ne $Spec.top) {
        try { $Shape.Top = [double]$Spec.top } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['fillColor'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.fillColor)) {
        try { $Shape.Fill.ForeColor.RGB = Convert-HexColorToBgrInt -Color ([string]$Spec.fillColor) } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['lineColor'] -and -not [string]::IsNullOrWhiteSpace([string]$Spec.lineColor)) {
        try { $Shape.Line.ForeColor.RGB = Convert-HexColorToBgrInt -Color ([string]$Spec.lineColor) } catch {}
    }
    if ($null -ne $Spec.PSObject.Properties['visible'] -and $null -ne $Spec.visible) {
        try { $Shape.Visible = [bool]$Spec.visible } catch {}
    }
}

function Convert-HexColorToBgrInt {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Color
    )

    $clean = $Color.Trim().TrimStart('#')
    if ($clean.Length -ne 6) {
        throw "Color must be a 6-digit hex value."
    }
    $r = [Convert]::ToInt32($clean.Substring(0, 2), 16)
    $g = [Convert]::ToInt32($clean.Substring(2, 2), 16)
    $b = [Convert]::ToInt32($clean.Substring(4, 2), 16)
    return ($r -bor ($g -shl 8) -bor ($b -shl 16))
}

function Ensure-DirectShapeDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Spec,
        [ValidateSet('create', 'update')]
        [string]$Mode
    )

    $name = [string]$Spec.name
    if ([string]::IsNullOrWhiteSpace($name)) {
        throw "Shape spec requires a name."
    }
    $existing = Find-DirectDrawing -Workbook $Workbook -Name $name -Kind 'shapes'
    if ($Mode -eq 'create' -and $null -ne $existing) {
        throw "Shape already exists: $name"
    }
    if ($Mode -eq 'update' -and $null -eq $existing) {
        throw "Shape not found: $name"
    }

    if ($null -ne $existing) {
        Set-DirectDrawingProperties -Shape $existing.shape -Spec $Spec
        return $existing.shape
    }

    $sheetName = if ($null -ne $Spec.PSObject.Properties['sheet']) { [string]$Spec.sheet } else { $null }
    if ([string]::IsNullOrWhiteSpace($sheetName)) {
        throw "Shape spec requires a sheet."
    }
    $topLeft = if ($null -ne $Spec.PSObject.Properties['topLeft']) { [string]$Spec.topLeft } else { $null }
    $left = if ($null -ne $Spec.PSObject.Properties['left']) { $Spec.left } else { $null }
    $top = if ($null -ne $Spec.PSObject.Properties['top']) { $Spec.top } else { $null }
    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sheetName
    $anchor = Get-WorksheetShapeAnchor -Worksheet $worksheet -TopLeft $topLeft -Left $left -Top $top
    $shapeType = if ($null -ne $Spec.PSObject.Properties['shapeType'] -and $null -ne $Spec.shapeType) { [int]$Spec.shapeType } else { 1 }
    $width = if ($null -ne $Spec.PSObject.Properties['width'] -and $null -ne $Spec.width) { [double]$Spec.width } else { 120.0 }
    $height = if ($null -ne $Spec.PSObject.Properties['height'] -and $null -ne $Spec.height) { [double]$Spec.height } else { 48.0 }
    $shape = $worksheet.Shapes.AddShape($shapeType, [double]$anchor.left, [double]$anchor.top, $width, $height)
    $shape.Name = $name
    Set-DirectDrawingProperties -Shape $shape -Spec $Spec
    return $shape
}

function Ensure-DirectPictureDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $Spec,
        [ValidateSet('add', 'update')]
        [string]$Mode
    )

    $name = [string]$Spec.name
    if ([string]::IsNullOrWhiteSpace($name)) {
        throw "Picture spec requires a name."
    }
    $existing = Find-DirectDrawing -Workbook $Workbook -Name $name -Kind 'pictures'
    if ($Mode -eq 'add' -and $null -ne $existing) {
        throw "Picture already exists: $name"
    }
    if ($Mode -eq 'update' -and $null -eq $existing) {
        throw "Picture not found: $name"
    }
    if ($null -ne $existing) {
        Set-DirectDrawingProperties -Shape $existing.shape -Spec $Spec
        return $existing.shape
    }

    $sheetName = if ($null -ne $Spec.PSObject.Properties['sheet']) { [string]$Spec.sheet } else { $null }
    $sourcePath = if ($null -ne $Spec.PSObject.Properties['sourcePath']) { [string]$Spec.sourcePath } else { $null }
    if ([string]::IsNullOrWhiteSpace($sheetName)) {
        throw "Picture spec requires a sheet."
    }
    if ([string]::IsNullOrWhiteSpace($sourcePath) -or -not (Test-Path -LiteralPath $sourcePath)) {
        throw "Picture spec requires an existing sourcePath."
    }
    $topLeft = if ($null -ne $Spec.PSObject.Properties['topLeft']) { [string]$Spec.topLeft } else { $null }
    $left = if ($null -ne $Spec.PSObject.Properties['left']) { $Spec.left } else { $null }
    $top = if ($null -ne $Spec.PSObject.Properties['top']) { $Spec.top } else { $null }
    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sheetName
    $anchor = Get-WorksheetShapeAnchor -Worksheet $worksheet -TopLeft $topLeft -Left $left -Top $top
    $width = if ($null -ne $Spec.PSObject.Properties['width'] -and $null -ne $Spec.width) { [double]$Spec.width } else { 96.0 }
    $height = if ($null -ne $Spec.PSObject.Properties['height'] -and $null -ne $Spec.height) { [double]$Spec.height } else { 96.0 }
    $shape = $worksheet.Shapes.AddPicture([System.IO.Path]::GetFullPath($sourcePath), $false, $true, [double]$anchor.left, [double]$anchor.top, $width, $height)
    $shape.Name = $name
    Set-DirectDrawingProperties -Shape $shape -Spec $Spec
    return $shape
}

function Remove-DirectDrawingDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [ValidateSet('shapes', 'pictures')]
        [string]$Kind
    )

    $existing = Find-DirectDrawing -Workbook $Workbook -Name $Name -Kind $Kind
    if ($null -eq $existing) {
        return $false
    }
    $existing.shape.Delete()
    return $true
}

function Resolve-ExcelSaveFormatSpec {
    param(
        [string]$SourcePath,
        [string]$TargetPath,
        [string]$TargetFormat
    )

    $normalized = $null
    if (-not [string]::IsNullOrWhiteSpace($TargetFormat)) {
        $normalized = $TargetFormat.Trim().ToLowerInvariant()
        if (-not $normalized.StartsWith('.')) {
            $normalized = ".$normalized"
        }
    }
    elseif (-not [string]::IsNullOrWhiteSpace($TargetPath)) {
        $normalized = [System.IO.Path]::GetExtension($TargetPath).ToLowerInvariant()
    }
    elseif (-not [string]::IsNullOrWhiteSpace($SourcePath)) {
        $normalized = [System.IO.Path]::GetExtension($SourcePath).ToLowerInvariant()
    }

    switch ($normalized) {
        '.xlsx' {
            return [pscustomobject]@{
                extension = '.xlsx'
                format = 'xlsx'
                description = 'Excel workbook'
                fileFormat = 51
                packageReadable = $true
                macroContainer = $false
                flatText = $false
                singleSheetOnly = $false
                legacy = $false
                openDocument = $false
            }
        }
        '.xlsm' {
            return [pscustomobject]@{
                extension = '.xlsm'
                format = 'xlsm'
                description = 'Excel macro-enabled workbook'
                fileFormat = 52
                packageReadable = $true
                macroContainer = $true
                flatText = $false
                singleSheetOnly = $false
                legacy = $false
                openDocument = $false
            }
        }
        '.xlsb' {
            return [pscustomobject]@{
                extension = '.xlsb'
                format = 'xlsb'
                description = 'Excel binary workbook'
                fileFormat = 50
                packageReadable = $false
                macroContainer = $true
                flatText = $false
                singleSheetOnly = $false
                legacy = $false
                openDocument = $false
            }
        }
        '.xls' {
            return [pscustomobject]@{
                extension = '.xls'
                format = 'xls'
                description = 'Excel 97-2003 workbook'
                fileFormat = 56
                packageReadable = $false
                macroContainer = $true
                flatText = $false
                singleSheetOnly = $false
                legacy = $true
                openDocument = $false
            }
        }
        '.csv' {
            return [pscustomobject]@{
                extension = '.csv'
                format = 'csv'
                description = 'UTF-8 CSV'
                fileFormat = 62
                packageReadable = $false
                macroContainer = $false
                flatText = $true
                singleSheetOnly = $true
                legacy = $false
                openDocument = $false
            }
        }
        '.txt' {
            return [pscustomobject]@{
                extension = '.txt'
                format = 'txt'
                description = 'Windows text'
                fileFormat = 20
                packageReadable = $false
                macroContainer = $false
                flatText = $true
                singleSheetOnly = $true
                legacy = $false
                openDocument = $false
            }
        }
        '.ods' {
            return [pscustomobject]@{
                extension = '.ods'
                format = 'ods'
                description = 'OpenDocument spreadsheet'
                fileFormat = 60
                packageReadable = $false
                macroContainer = $false
                flatText = $false
                singleSheetOnly = $false
                legacy = $false
                openDocument = $true
            }
        }
        default {
            throw "Unsupported target workbook format: $normalized"
        }
    }
}

function Resolve-WorkbookTargetPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [string]$TargetPath,
        [string]$TargetFormat,
        [string]$Suffix = ''
    )

    $formatSpec = Resolve-ExcelSaveFormatSpec -SourcePath $SourcePath -TargetPath $TargetPath -TargetFormat $TargetFormat
    if (-not [string]::IsNullOrWhiteSpace($TargetPath)) {
        return [pscustomobject]@{
            path = [System.IO.Path]::GetFullPath($TargetPath)
            format = $formatSpec
        }
    }

    $sourceFullPath = [System.IO.Path]::GetFullPath($SourcePath)
    $sourceDirectory = Split-Path -Parent $sourceFullPath
    $sourceStem = [System.IO.Path]::GetFileNameWithoutExtension($sourceFullPath)
    $targetLeaf = '{0}{1}{2}' -f $sourceStem, $Suffix, $formatSpec.extension
    return [pscustomobject]@{
        path = [System.IO.Path]::Combine($sourceDirectory, $targetLeaf)
        format = $formatSpec
    }
}

function Get-WorkbookCompatibilityReport {
    param(
        [Parameter(Mandatory = $true)]
        $InspectionPayload,
        [string]$TargetPath,
        [string]$TargetFormat
    )

    $formatSpec = Resolve-ExcelSaveFormatSpec `
        -SourcePath ([string]$InspectionPayload.workbookPath) `
        -TargetPath $TargetPath `
        -TargetFormat $TargetFormat

    $counts = if ($null -ne $InspectionPayload.PSObject.Properties['counts']) { $InspectionPayload.counts } else { [pscustomobject]@{} }
    $workbookMetadata = $null
    if ($null -ne $InspectionPayload.PSObject.Properties['workbook']) {
        $workbookMetadata = $InspectionPayload.workbook
    }

    $sourceFormat = [string]$InspectionPayload.sourceFormat
    $hasVbaProject = $false
    if ($null -ne $workbookMetadata -and $null -ne $workbookMetadata.PSObject.Properties['hasVbaProject']) {
        $hasVbaProject = [bool]$workbookMetadata.hasVbaProject
    }
    elseif ($sourceFormat -in @('.xlsm', '.xlsb', '.xlam', '.xltm', '.xls')) {
        $hasVbaProject = $true
    }

    $findings = New-Object System.Collections.Generic.List[object]
    $overallRisk = 'low'

    function Add-CompatibilityFinding {
        param(
            [string]$Severity,
            [string]$Area,
            [string]$Message
        )

        $currentRisk = Get-Variable -Name overallRisk -Scope 1 -ValueOnly
        $nextRisk = switch ($currentRisk) {
            'high' { 'high' }
            'medium' { if ($Severity -eq 'high') { 'high' } else { 'medium' } }
            default {
                if ($Severity -eq 'high') { 'high' }
                elseif ($Severity -eq 'medium') { 'medium' }
                else { 'low' }
            }
        }
        Set-Variable -Name overallRisk -Scope 1 -Value $nextRisk
        $findings.Add([pscustomobject]@{
            severity = $Severity
            area = $Area
            message = $Message
        }) | Out-Null
    }

    function Get-CompatibilityCount {
        param(
            [Parameter(Mandatory = $true)]
            [string]$Name
        )

        $countObject = Get-Variable -Name counts -Scope 1 -ValueOnly
        if ($null -eq $countObject) {
            return 0
        }
        if ($null -eq $countObject.PSObject.Properties[$Name]) {
            return 0
        }
        $rawValue = $countObject.$Name
        if ($null -eq $rawValue -or [string]::IsNullOrWhiteSpace([string]$rawValue)) {
            return 0
        }
        return [int]$rawValue
    }

    $sheetsCount = Get-CompatibilityCount -Name 'sheets'
    $formulasCount = Get-CompatibilityCount -Name 'formulas'
    $tablesCount = Get-CompatibilityCount -Name 'tables'
    $namesCount = Get-CompatibilityCount -Name 'names'
    $commentsCount = Get-CompatibilityCount -Name 'comments'
    $hyperlinksCount = Get-CompatibilityCount -Name 'hyperlinks'
    $chartsCount = Get-CompatibilityCount -Name 'charts'
    $pivotsCount = Get-CompatibilityCount -Name 'pivots'
    $pqCount = Get-CompatibilityCount -Name 'pq'
    $connectionsCount = Get-CompatibilityCount -Name 'connections'
    $modelTablesCount = Get-CompatibilityCount -Name 'modelTables'

    if ($formatSpec.flatText) {
        if ($sheetsCount -gt 1) {
            Add-CompatibilityFinding -Severity 'high' -Area 'worksheets' -Message 'Flat-text exports preserve only one worksheet per file. Use a per-sheet export plan before converting.'
        }
        if ($formulasCount -gt 0) {
            Add-CompatibilityFinding -Severity 'high' -Area 'formulas' -Message 'Formulas will be written as current displayed values in flat-text formats; formula logic will not survive.'
        }
        foreach ($surface in @(
                @{ name = 'tables'; count = $tablesCount; message = 'Tables and structured references do not survive CSV/TXT export.' },
                @{ name = 'names'; count = $namesCount; message = 'Defined names are discarded by CSV/TXT export.' },
                @{ name = 'comments'; count = $commentsCount; message = 'Comments and notes are discarded by CSV/TXT export.' },
                @{ name = 'hyperlinks'; count = $hyperlinksCount; message = 'Hyperlink objects are not preserved as workbook objects in CSV/TXT export.' },
                @{ name = 'charts'; count = $chartsCount; message = 'Charts are lost when exporting to CSV/TXT.' },
                @{ name = 'pivots'; count = $pivotsCount; message = 'PivotTables and PivotCharts are lost when exporting to CSV/TXT.' },
                @{ name = 'power-query'; count = $pqCount; message = 'Power Query definitions are not preserved in flat-text exports.' },
                @{ name = 'connections'; count = $connectionsCount; message = 'Workbook connections are not preserved in flat-text exports.' },
                @{ name = 'data-model'; count = $modelTablesCount; message = 'The Data Model is not preserved in flat-text exports.' }
            )) {
            if ([int]$surface.count -gt 0) {
                Add-CompatibilityFinding -Severity 'high' -Area $surface.name -Message $surface.message
            }
        }
        Add-CompatibilityFinding -Severity 'medium' -Area 'formatting' -Message 'Cell formats, workbook themes, print settings, and metadata do not round-trip through CSV/TXT.'
    }
    elseif ($formatSpec.extension -eq '.xlsx') {
        if ($hasVbaProject) {
            Add-CompatibilityFinding -Severity 'high' -Area 'vba' -Message 'Saving to .xlsx removes VBA project content because .xlsx is a macro-free container.'
        }
    }
    elseif ($formatSpec.extension -eq '.ods') {
        if ($hasVbaProject) {
            Add-CompatibilityFinding -Severity 'high' -Area 'vba' -Message 'VBA projects do not round-trip to .ods.'
        }
        if ($pqCount -gt 0 -or $connectionsCount -gt 0 -or $modelTablesCount -gt 0) {
            Add-CompatibilityFinding -Severity 'high' -Area 'data-integration' -Message 'Power Query, workbook connections, and Data Model artifacts are not reliable in .ods exports.'
        }
        if ($pivotsCount -gt 0 -or $chartsCount -gt 0) {
            Add-CompatibilityFinding -Severity 'medium' -Area 'analytics' -Message 'Pivot and chart fidelity may degrade when exporting to .ods; validate layouts after conversion.'
        }
    }
    elseif ($formatSpec.extension -eq '.xls') {
        Add-CompatibilityFinding -Severity 'medium' -Area 'legacy' -Message 'Legacy .xls compatibility is heuristic here; modern Excel features can degrade even when the file saves successfully.'
        if ($pqCount -gt 0 -or $connectionsCount -gt 0 -or $modelTablesCount -gt 0) {
            Add-CompatibilityFinding -Severity 'high' -Area 'modern-data-stack' -Message 'Power Query, workbook connections, and Data Model artifacts are not safe targets for legacy .xls.'
        }
        if ($formulasCount -gt 0) {
            Add-CompatibilityFinding -Severity 'medium' -Area 'formulas' -Message 'Modern formulas and dynamic-array behavior may not round-trip to .xls; validate calc results after conversion.'
        }
    }
    elseif ($formatSpec.extension -eq '.xlsb') {
        if ($pqCount -gt 0 -or $connectionsCount -gt 0 -or $modelTablesCount -gt 0) {
            Add-CompatibilityFinding -Severity 'low' -Area 'refresh' -Message 'Binary workbooks usually preserve refresh artifacts, but post-conversion refresh should still be validated.'
        }
    }

    return [pscustomobject]@{
        targetFormat = $formatSpec.format
        targetExtension = $formatSpec.extension
        targetPath = if ([string]::IsNullOrWhiteSpace($TargetPath)) { $null } else { [System.IO.Path]::GetFullPath($TargetPath) }
        heuristic = $true
        overallRisk = $overallRisk
        findings = @($findings.ToArray())
        recommendedPlan = switch ($formatSpec.extension) {
            '.csv' { 'Export one worksheet at a time, capture workbook logic separately in manifests, and treat the result as a downstream data extract rather than a workbook round-trip.' }
            '.txt' { 'Export one worksheet at a time, preserve schema and workbook logic outside the text file, and treat the result as a flat interchange artifact.' }
            '.xlsx' { 'Use .xlsx only for macro-free destinations. If VBA must survive, prefer .xlsm or .xlsb.' }
            '.xls' { 'Create a compatibility copy, recalculate, and verify formulas, queries, and row/column limits before replacing the source workbook.' }
            '.ods' { 'Use .ods only when OpenDocument interoperability matters more than Excel-specific automation, queries, or VBA.' }
            default { 'Save a copy, refresh/recalculate, and inspect the converted workbook before promoting it.' }
        }
    }
}

function Invoke-WorkbookRepairOpen {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [switch]$Visible,
        [ValidateSet(1, 2)]
        [int]$CorruptLoad = 1
    )

    if (-not (Test-Path -LiteralPath $WorkbookPath)) {
        throw "Workbook not found: $WorkbookPath"
    }

    $script:ExcelFoundryLastOpenDiagnostics = $null
    $excel = $null
    $workbook = $null
    try {
        $excel = New-Object -ComObject Excel.Application
    }
    catch {
        throw "Excel COM automation is unavailable on this host."
    }

    [void](Try-SetProperty -Target $excel -Name 'Visible' -Value ([bool]$Visible))
    [void](Try-SetProperty -Target $excel -Name 'DisplayAlerts' -Value $false)
    [void](Try-SetProperty -Target $excel -Name 'ScreenUpdating' -Value $false)
    [void](Try-SetProperty -Target $excel -Name 'EnableEvents' -Value $false)
    [void](Try-SetProperty -Target $excel -Name 'AskToUpdateLinks' -Value $false)
    [void](Try-SetProperty -Target $excel -Name 'AutomationSecurity' -Value 3)

    try {
        $attempts = @(
            {
                Invoke-ExcelComWithRetry -Description 'Opening workbook in recovery mode' -MaxAttempts 10 -DelayMilliseconds 500 -Operation {
                    $excel.Workbooks.Open($WorkbookPath, 0, $true, $null, $null, $null, $true, $null, $null, $false, $false, $null, $false, $true, $CorruptLoad)
                }
            },
            {
                Invoke-ExcelComWithRetry -Description 'Opening workbook in recovery mode' -MaxAttempts 10 -DelayMilliseconds 500 -Operation {
                    $excel.Workbooks.Open($WorkbookPath, 0, $true, $null, $null, $null, $true, $null, $null, $false, $false, $null, $false, $true)
                }
            },
            {
                Invoke-ExcelComWithRetry -Description 'Opening workbook in recovery mode' -MaxAttempts 10 -DelayMilliseconds 500 -Operation {
                    $excel.Workbooks.Open($WorkbookPath, 0, $true)
                }
            }
        )

        foreach ($attempt in $attempts) {
            try {
                $workbook = & $attempt
                if ($null -ne $workbook) {
                    break
                }
            }
            catch {
            }
        }

        if ($null -eq $workbook) {
            throw "Unable to open workbook in recovery mode."
        }
        return [pscustomobject]@{
            Excel = $excel
            Workbook = $workbook
            ReadOnly = $true
            Visible = [bool]$Visible
            RecoveryMode = $CorruptLoad
        }
    }
    catch {
        try {
            Invoke-ExcelQuitSafely -Excel $excel -Description 'Quitting Excel after failed recovery open' -SwallowErrors
        }
        finally {
            Release-ComObjectSafely -Object $workbook
            Release-ComObjectSafely -Object $excel
            [gc]::Collect()
            [gc]::WaitForPendingFinalizers()
        }
        throw
    }
}

function Invoke-WorkbookDocumentInspection {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $InspectionPayload,
        [switch]$Apply
    )

    $modules = New-Object System.Collections.Generic.List[object]
    try {
        $inspectors = $Workbook.DocumentInspectors
        if ($null -ne $inspectors) {
            for ($index = 1; $index -le [int]$inspectors.Count; $index++) {
                $inspector = $inspectors.Item($index)
                $status = 0
                $result = ''
                $fixStatus = $null
                $fixResult = $null
                $inspectorName = "Inspector $index"
                $inspectorDescription = $null
                try {
                    $statusRef = [ref]$status
                    $resultRef = [ref]$result
                    $inspector.Inspect($statusRef, $resultRef) | Out-Null
                    try { $inspectorName = [string]$inspector.Name } catch {}
                    try { $inspectorDescription = [string]$inspector.Description } catch {}
                    if ($Apply -and [int]$status -ne 0) {
                        $fixStatus = 0
                        $fixResult = ''
                        $fixStatusRef = [ref]$fixStatus
                        $fixResultRef = [ref]$fixResult
                        $inspector.Fix($fixStatusRef, $fixResultRef) | Out-Null
                    }
                }
                catch {
                    $result = $_.Exception.Message
                }

                $modules.Add([pscustomobject]@{
                    name = $inspectorName
                    description = $inspectorDescription
                    status = [int]$status
                    result = [string]$result
                    fixStatus = if ($null -ne $fixStatus) { [int]$fixStatus } else { $null }
                    fixResult = $fixResult
                }) | Out-Null
            }
        }
    }
    catch {
        $modules.Add([pscustomobject]@{
            name = 'DocumentInspectors'
            description = $null
            status = -1
            result = $_.Exception.Message
            fixStatus = $null
            fixResult = $null
        }) | Out-Null
    }

    $manualFindings = New-Object System.Collections.Generic.List[object]
    $workbookMetadata = if ($null -ne $InspectionPayload.PSObject.Properties['workbook']) { $InspectionPayload.workbook } else { $null }
    $customPropertiesCount = 0
    if ($null -ne $workbookMetadata -and
        $null -ne $workbookMetadata.PSObject.Properties['properties'] -and
        $null -ne $workbookMetadata.properties.PSObject.Properties['custom']) {
        $customPropertiesCount = @($workbookMetadata.properties.custom.PSObject.Properties).Count
    }
    $commentsCount = if ($null -ne $InspectionPayload.counts.PSObject.Properties['comments']) { [int]$InspectionPayload.counts.comments } else { 0 }
    $hyperlinksCount = if ($null -ne $InspectionPayload.counts.PSObject.Properties['hyperlinks']) { [int]$InspectionPayload.counts.hyperlinks } else { 0 }
    $externalLinks = if ($null -ne $workbookMetadata -and $null -ne $workbookMetadata.PSObject.Properties['hasExternalLinks']) { [bool]$workbookMetadata.hasExternalLinks } else { $false }
    $hiddenSheets = @()
    if ($null -ne $InspectionPayload.PSObject.Properties['sheets']) {
        $hiddenSheets = @($InspectionPayload.sheets | Where-Object { [string]$_.visibility -ne 'visible' } | ForEach-Object { [string]$_.name })
    }

    if ($commentsCount -gt 0) {
        $manualFindings.Add([pscustomobject]@{
            area = 'comments'
            status = 'review'
            message = "Workbook contains $commentsCount comment or note object(s) that should be reviewed before external sharing."
        }) | Out-Null
    }
    if ($customPropertiesCount -gt 0) {
        $propertyNoun = if ($customPropertiesCount -eq 1) { 'property' } else { 'properties' }
        $manualFindings.Add([pscustomobject]@{
            area = 'metadata'
            status = 'review'
            message = "Workbook contains $customPropertiesCount custom document $propertyNoun."
        }) | Out-Null
    }
    if ($hiddenSheets.Count -gt 0) {
        $manualFindings.Add([pscustomobject]@{
            area = 'hidden-sheets'
            status = 'review'
            message = "Workbook contains hidden or very-hidden sheets: $($hiddenSheets -join ', ')."
        }) | Out-Null
    }
    if ($externalLinks) {
        $manualFindings.Add([pscustomobject]@{
            area = 'external-links'
            status = 'review'
            message = 'Workbook contains external links or linked sources that should be validated before distribution.'
        }) | Out-Null
    }
    if ($hyperlinksCount -gt 0) {
        $manualFindings.Add([pscustomobject]@{
            area = 'hyperlinks'
            status = 'review'
            message = "Workbook contains $hyperlinksCount hyperlink object(s); validate whether outbound destinations are share-safe."
        }) | Out-Null
    }

    return [pscustomobject]@{
        applied = [bool]$Apply
        modules = @($modules.ToArray())
        manualFindings = @($manualFindings.ToArray())
    }
}

function Get-WorkbookLinkInventory {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook
    )

    $typeMap = @(
        @{ id = 1; name = 'excel'; label = 'excel-links'; canBreak = $true; canRepoint = $true },
        @{ id = 2; name = 'ole'; label = 'ole-links'; canBreak = $true; canRepoint = $true }
    )

    $links = New-Object System.Collections.Generic.List[object]
    foreach ($typeSpec in $typeMap) {
        $sources = $null
        try {
            $sources = $Workbook.LinkSources($typeSpec.id)
        }
        catch {
            $sources = $null
        }
        if ($null -eq $sources) {
            continue
        }

        foreach ($source in @($sources)) {
            if ($null -eq $source) {
                continue
            }
            $links.Add([pscustomobject]@{
                name = [string]$source
                type = [string]$typeSpec.name
                typeLabel = [string]$typeSpec.label
                typeId = [int]$typeSpec.id
                canBreak = [bool]$typeSpec.canBreak
                canRepoint = [bool]$typeSpec.canRepoint
            }) | Out-Null
        }
    }

    return @($links.ToArray() | Sort-Object type, name -Unique)
}

function Invoke-WorkbookBreakLinks {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [string[]]$Names = @(),
        [switch]$All
    )

    $inventory = @(Get-WorkbookLinkInventory -Workbook $Workbook)
    $targets = if ($All -or @($Names).Count -eq 0) {
        @($inventory)
    }
    else {
        @($inventory | Where-Object { [string]$_.name -in @($Names) })
    }

    $broken = New-Object System.Collections.Generic.List[object]
    foreach ($target in @($targets)) {
        $Workbook.BreakLink([string]$target.name, [int]$target.typeId)
        $broken.Add([pscustomobject]@{
            name = [string]$target.name
            type = [string]$target.type
        }) | Out-Null
    }

    return [pscustomobject]@{
        requestedAll = [bool]$All
        requestedNames = @($Names)
        broken = @($broken.ToArray())
        remaining = @(Get-WorkbookLinkInventory -Workbook $Workbook)
    }
}

function Invoke-WorkbookRepointLinks {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [object[]]$Mappings
    )

    $applied = New-Object System.Collections.Generic.List[object]
    foreach ($mapping in @($Mappings)) {
        $from = if ($null -ne $mapping.PSObject.Properties['from']) { [string]$mapping.from } else { $null }
        $to = if ($null -ne $mapping.PSObject.Properties['to']) { [string]$mapping.to } else { $null }
        if ([string]::IsNullOrWhiteSpace($from) -or [string]::IsNullOrWhiteSpace($to)) {
            throw "Each link mapping requires from/to values."
        }
        $typeId = if ($null -ne $mapping.PSObject.Properties['typeId']) {
            [int]$mapping.typeId
        }
        elseif ($null -ne $mapping.PSObject.Properties['type']) {
            switch ([string]$mapping.type) {
                'excel' { 1 }
                'ole' { 2 }
                default { 1 }
            }
        }
        else {
            1
        }

        $Workbook.ChangeLink($from, $to, $typeId)
        $applied.Add([pscustomobject]@{
            from = $from
            to = $to
            typeId = $typeId
        }) | Out-Null
    }

    return [pscustomobject]@{
        applied = @($applied.ToArray())
        links = @(Get-WorkbookLinkInventory -Workbook $Workbook)
    }
}

function Invoke-WorkbookRemoveDocumentInfo {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [int[]]$Types = @(99)
    )

    $results = New-Object System.Collections.Generic.List[object]
    foreach ($typeId in @($Types | Where-Object { $null -ne $_ })) {
        try {
            $Workbook.RemoveDocumentInformation([int]$typeId)
            $results.Add([pscustomobject]@{
                typeId = [int]$typeId
                removed = $true
                error = $null
            }) | Out-Null
        }
        catch {
            $results.Add([pscustomobject]@{
                typeId = [int]$typeId
                removed = $false
                error = $_.Exception.Message
            }) | Out-Null
        }
    }

    return @($results.ToArray())
}

function Invoke-WorkbookSafeExport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string]$TargetPath,
        [string]$TargetFormat,
        [string]$SpecJson,
        [string]$SpecFile,
        [switch]$Visible
    )

    $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
    $breakLinks = $true
    $linkNames = @()
    $removeDocInfoTypes = @(99)
    $runDocumentInspectors = $true
    if ($null -ne $spec) {
        if ($null -ne $spec.PSObject.Properties['breakLinks']) { $breakLinks = [bool]$spec.breakLinks }
        if ($null -ne $spec.PSObject.Properties['linkNames']) { $linkNames = @($spec.linkNames) }
        if ($null -ne $spec.PSObject.Properties['removeDocumentInfoTypes']) { $removeDocInfoTypes = @($spec.removeDocumentInfoTypes | ForEach-Object { [int]$_ }) }
        if ($null -ne $spec.PSObject.Properties['runDocumentInspectors']) { $runDocumentInspectors = [bool]$spec.runDocumentInspectors }
    }

    $normalizedTargetFormat = $null
    if (-not [string]::IsNullOrWhiteSpace($TargetFormat)) {
        $normalizedTargetFormat = $TargetFormat.Trim().ToLowerInvariant()
        if (-not $normalizedTargetFormat.StartsWith('.')) {
            $normalizedTargetFormat = ".$normalizedTargetFormat"
        }
    }
    elseif (-not [string]::IsNullOrWhiteSpace($TargetPath)) {
        $normalizedTargetFormat = [System.IO.Path]::GetExtension($TargetPath).ToLowerInvariant()
    }

    $target = if ($normalizedTargetFormat -eq '.pdf') {
        $targetPathValue = if (-not [string]::IsNullOrWhiteSpace($TargetPath)) {
            [System.IO.Path]::GetFullPath($TargetPath)
        }
        else {
            $sourceFullPath = [System.IO.Path]::GetFullPath($WorkbookPath)
            $sourceDirectory = Split-Path -Parent $sourceFullPath
            $sourceStem = [System.IO.Path]::GetFileNameWithoutExtension($sourceFullPath)
            [System.IO.Path]::Combine($sourceDirectory, "$sourceStem.share-safe.pdf")
        }
        [pscustomobject]@{
            path = $targetPathValue
            format = [pscustomobject]@{
                extension = '.pdf'
                format = 'pdf'
                description = 'PDF'
                fileFormat = $null
            }
        }
    }
    else {
        Resolve-WorkbookTargetPath `
            -SourcePath $WorkbookPath `
            -TargetPath $TargetPath `
            -TargetFormat $TargetFormat `
            -Suffix '.share-safe'
    }

    Ensure-ParentDirectory -Path $target.path
    $sourceExtension = [System.IO.Path]::GetExtension($WorkbookPath)
    $temporaryCopyPath = Join-Path ([System.IO.Path]::GetTempPath()) ("excel-foundry-safe-export-{0}{1}" -f [System.Guid]::NewGuid().ToString('N'), $sourceExtension)
    $sourceContext = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible
    try {
        $sourceContext.Workbook.SaveCopyAs($temporaryCopyPath)
    }
    finally {
        Close-ExcelWorkbook -Context $sourceContext -SaveChanges:$false
    }

    $copyContext = Open-ExcelWorkbook -WorkbookPath $temporaryCopyPath -Visible:$Visible
    try {
        $inspection = Get-ExcelWorkbookLifecycleInspection `
            -WorkbookPath $temporaryCopyPath `
            -Visible:$Visible `
            -Backend 'auto'
        $documentInspection = if ($runDocumentInspectors) {
            Invoke-WorkbookDocumentInspection -Workbook $copyContext.Workbook -InspectionPayload $inspection -Apply
        }
        else {
            [pscustomobject]@{ applied = $false; modules = @(); manualFindings = @() }
        }
        $docInfoResults = Invoke-WorkbookRemoveDocumentInfo -Workbook $copyContext.Workbook -Types $removeDocInfoTypes
        $beforeLinks = @(Get-WorkbookLinkInventory -Workbook $copyContext.Workbook)
        $brokenLinks = if ($breakLinks) {
            Invoke-WorkbookBreakLinks -Workbook $copyContext.Workbook -Names $linkNames -All:($linkNames.Count -eq 0)
        }
        else {
            [pscustomobject]@{ requestedAll = $false; requestedNames = @($linkNames); broken = @(); remaining = $beforeLinks }
        }

        if ($target.format.format -eq 'pdf') {
            if ([System.IO.Path]::GetExtension($target.path).ToLowerInvariant() -ne '.pdf') {
                $target.path = [System.IO.Path]::ChangeExtension($target.path, '.pdf')
            }
            Invoke-LateMethod -Target $copyContext.Workbook -Name 'ExportAsFixedFormat' -Arguments @(0, $target.path) | Out-Null
        }
        elseif ($target.format.extension -ne [System.IO.Path]::GetExtension($target.path).ToLowerInvariant()) {
            $target.path = [System.IO.Path]::ChangeExtension($target.path, $target.format.extension)
            $copyContext.Workbook.SaveAs($target.path, $target.format.fileFormat)
        }
        else {
            $copyContext.Workbook.SaveAs($target.path, $target.format.fileFormat)
        }

        return [pscustomobject]@{
            command = 'workbook-safe-export'
            backend = 'excel'
            workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
            targetPath = [string]$target.path
            targetFormat = [string]$target.format.format
            documentInspection = $documentInspection
            removedDocumentInfo = @($docInfoResults)
            linksBefore = $beforeLinks
            linkOperations = $brokenLinks
        }
    }
    finally {
        Close-ExcelWorkbook -Context $copyContext -SaveChanges:$false
        if (Test-Path -LiteralPath $temporaryCopyPath) {
            Remove-Item -LiteralPath $temporaryCopyPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function New-WorkbookModelPlatformLimitedMutation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string]$Name,
        $Spec
    )

    $surface = ($Command -split '-')[0]
    return [pscustomobject]@{
        command = $Command
        backend = 'excel'
        workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
        surface = $surface
        name = $Name
        spec = $Spec
        changed = $false
        status = 'platform-limited'
        platformLimits = @(
            'This desktop Excel object model does not expose a stable writable automation API for this Data Model artifact on every host.',
            'Excel Foundry preserves and inspects this artifact and reports the mutation plan instead of emitting an unsafe best-effort rewrite.'
        )
        message = "Use model inspect to verify current Data Model state; apply this $surface change in a host that exposes writable model APIs or through a dedicated BI tooling workflow."
    }
}

function Test-WorkbookModelHasWritableTables {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook
    )

    try {
        return @($Workbook.Model.ModelTables).Count -gt 0
    }
    catch {
        return $false
    }
}

function Invoke-DirectExcelWorkbookCommand {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('workbook-save-as', 'workbook-convert', 'workbook-repair', 'workbook-compatibility', 'workbook-document-inspect', 'workbook-links', 'workbook-break-links', 'workbook-repoint-links', 'workbook-safe-export', 'table-get', 'table-create', 'table-update', 'table-delete', 'query-get', 'query-set', 'query-delete', 'query-refresh', 'connection-list', 'connection-get', 'connection-update', 'connection-delete', 'chart-list', 'chart-get', 'chart-create', 'chart-update', 'chart-delete', 'shape-list', 'shape-get', 'shape-create', 'shape-update', 'shape-delete', 'picture-list', 'picture-get', 'picture-add', 'picture-update', 'picture-delete', 'control-list', 'control-get', 'pivot-list', 'pivot-get', 'pivot-create', 'pivot-update', 'pivot-delete', 'pivot-refresh', 'slicer-list', 'slicer-get', 'slicer-create', 'slicer-update', 'slicer-delete', 'slicer-clear', 'slicer-set-filter', 'timeline-list', 'timeline-get', 'timeline-create', 'timeline-update', 'timeline-delete', 'timeline-clear', 'timeline-set-range', 'model-inspect', 'measure-list', 'measure-get', 'measure-set', 'measure-delete', 'relationship-list', 'relationship-get', 'relationship-set', 'relationship-delete', 'hierarchy-list', 'hierarchy-get', 'hierarchy-set', 'hierarchy-delete', 'kpi-list', 'kpi-get', 'kpi-set', 'kpi-delete', 'perspective-list', 'perspective-get', 'perspective-set', 'perspective-delete')]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Table = @(),
        [string[]]$QueryName = @(),
        [string[]]$Name = @(),
        [string[]]$Connection = @(),
        [string[]]$Chart = @(),
        [string[]]$Pivot = @(),
        [string[]]$Slicer = @(),
        [string[]]$Timeline = @(),
        [string]$TargetPath,
        [string]$TargetFormat,
        [string]$SpecJson,
        [string]$SpecFile,
        [ValidateSet('repair', 'extract')]
        [string]$Mode = 'repair',
        [switch]$Apply,
        [switch]$Visible
    )

    if ($Command -eq 'workbook-compatibility') {
        if ([string]::IsNullOrWhiteSpace($TargetPath) -and [string]::IsNullOrWhiteSpace($TargetFormat)) {
            throw "workbook compatibility requires --target-path or --target-format"
        }
        $inspection = Get-ExcelWorkbookLifecycleInspection `
            -WorkbookPath $WorkbookPath `
            -Visible:$Visible `
            -Backend 'auto'
        return [pscustomobject]@{
            command = $Command
            backend = 'multi-engine'
            workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
            compatibility = Get-WorkbookCompatibilityReport -InspectionPayload $inspection -TargetPath $TargetPath -TargetFormat $TargetFormat
        }
    }

    if ($Command -eq 'workbook-repair') {
        $recoveryMode = if ($Mode -eq 'extract') { 2 } else { 1 }
        $repairTargetFormat = if ([string]::IsNullOrWhiteSpace($TargetFormat)) { [System.IO.Path]::GetExtension($WorkbookPath) } else { $TargetFormat }
        $repairSuffix = if ($Mode -eq 'extract') { '.extracted' } else { '.repaired' }
        $target = Resolve-WorkbookTargetPath `
            -SourcePath $WorkbookPath `
            -TargetPath $TargetPath `
            -TargetFormat $repairTargetFormat `
            -Suffix $repairSuffix
        $context = Invoke-WorkbookRepairOpen -WorkbookPath $WorkbookPath -Visible:$Visible -CorruptLoad $recoveryMode
        try {
            Ensure-ParentDirectory -Path $target.path
            $context.Workbook.SaveAs($target.path, $target.format.fileFormat)
            return [pscustomobject]@{
                command = $Command
                backend = 'excel'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                targetPath = [string]$target.path
                targetFormat = [string]$target.format.format
                recoveryMode = if ($Mode -eq 'extract') { 'extract-data' } else { 'repair' }
                openDiagnostics = $script:ExcelFoundryLastOpenDiagnostics
                saved = $true
            }
        }
        finally {
            Close-ExcelWorkbook -Context $context -SaveChanges:$false
        }
    }

    if ($Command -eq 'workbook-safe-export') {
        if ([string]::IsNullOrWhiteSpace($TargetPath) -and [string]::IsNullOrWhiteSpace($TargetFormat)) {
            throw "workbook safe-export requires --target-path or --target-format"
        }
        return Invoke-WorkbookSafeExport `
            -WorkbookPath $WorkbookPath `
            -TargetPath $TargetPath `
            -TargetFormat $TargetFormat `
            -SpecJson $SpecJson `
            -SpecFile $SpecFile `
            -Visible:$Visible
    }

    if ($Command -in @('workbook-save-as', 'workbook-convert') -and
        [string]::IsNullOrWhiteSpace($TargetPath) -and
        [string]::IsNullOrWhiteSpace($TargetFormat)) {
        throw ("{0} requires --target-path or --target-format" -f (($Command -replace '^workbook-', 'workbook ') -replace '-', ' '))
    }

    $readOnlyDirectCommands = @('workbook-links', 'table-get', 'query-get', 'connection-list', 'connection-get', 'chart-list', 'chart-get', 'shape-list', 'shape-get', 'picture-list', 'picture-get', 'control-list', 'control-get', 'pivot-list', 'pivot-get', 'slicer-list', 'slicer-get', 'timeline-list', 'timeline-get')
    $packageFallbackCommands = @('table-get', 'query-get', 'connection-list', 'connection-get', 'chart-list', 'chart-get', 'pivot-list', 'pivot-get')
    if ($Command -in @('measure-set', 'relationship-set', 'hierarchy-set', 'kpi-set', 'perspective-set')) {
        $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
        if ($null -eq $spec) {
            throw "$(($Command -replace '-', ' ')) requires --spec-json or --spec-file"
        }
        $modelName = if ($Command -eq 'relationship-set') {
            Get-WorkbookModelRelationshipId -ForeignKeyTable ([string]$spec.foreignKeyTable) -ForeignKeyColumn ([string]$spec.foreignKeyColumn) -PrimaryKeyTable ([string]$spec.primaryKeyTable) -PrimaryKeyColumn ([string]$spec.primaryKeyColumn)
        }
        else {
            [string]$spec.name
        }
        return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name $modelName -Spec $spec
    }
    if ($Command -in @('measure-delete', 'relationship-delete', 'hierarchy-delete', 'kpi-delete', 'perspective-delete')) {
        if (@($Name).Count -lt 1) {
            throw "$(($Command -replace '-', ' ')) requires --name"
        }
        return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$Name[0]) -Spec $null
    }
    $context = $null
    try {
        if ($Command -in $readOnlyDirectCommands) {
            $context = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible -ReadOnlyIntent
        }
        else {
            $context = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible
        }
    }
    catch {
        if ($Command -in $packageFallbackCommands -and (Test-OoxmlPackageWorkbook -WorkbookPath $WorkbookPath)) {
            return Invoke-DirectPackageReadFallback `
                -Command $Command `
                -WorkbookPath $WorkbookPath `
                -Table $Table `
                -QueryName $QueryName `
                -Connection $Connection `
                -Chart $Chart `
                -Pivot $Pivot `
                -Slicer $Slicer `
                -Timeline $Timeline
        }
        throw
    }

    $saveChanges = $false
    try {
        switch ($Command) {
            'workbook-save-as' {
                if ([string]::IsNullOrWhiteSpace($TargetPath) -and [string]::IsNullOrWhiteSpace($TargetFormat)) {
                    throw "workbook save-as requires --target-path or --target-format"
                }
                $target = Resolve-WorkbookTargetPath -SourcePath $WorkbookPath -TargetPath $TargetPath -TargetFormat $TargetFormat -Suffix ''
                $inspection = Get-ExcelWorkbookLifecycleInspection `
                    -WorkbookPath $WorkbookPath `
                    -Visible:$Visible `
                    -Backend 'auto'
                $compatibility = Get-WorkbookCompatibilityReport -InspectionPayload $inspection -TargetPath $target.path -TargetFormat $target.format.extension
                Ensure-ParentDirectory -Path $target.path
                $context.Workbook.SaveAs($target.path, $target.format.fileFormat)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    targetPath = [string]$target.path
                    targetFormat = [string]$target.format.format
                    compatibility = $compatibility
                    saved = $true
                }
            }
            'workbook-convert' {
                if ([string]::IsNullOrWhiteSpace($TargetPath) -and [string]::IsNullOrWhiteSpace($TargetFormat)) {
                    throw "workbook convert requires --target-path or --target-format"
                }
                $target = Resolve-WorkbookTargetPath -SourcePath $WorkbookPath -TargetPath $TargetPath -TargetFormat $TargetFormat -Suffix '.converted'
                $inspection = Get-ExcelWorkbookLifecycleInspection `
                    -WorkbookPath $WorkbookPath `
                    -Visible:$Visible `
                    -Backend 'auto'
                $compatibility = Get-WorkbookCompatibilityReport -InspectionPayload $inspection -TargetPath $target.path -TargetFormat $target.format.extension
                Ensure-ParentDirectory -Path $target.path
                $sourceExtension = [System.IO.Path]::GetExtension($WorkbookPath)
                $temporaryCopyPath = Join-Path ([System.IO.Path]::GetTempPath()) ("excel-foundry-convert-{0}{1}" -f [System.Guid]::NewGuid().ToString('N'), $sourceExtension)
                $context.Workbook.SaveCopyAs($temporaryCopyPath)
                $copyContext = Open-ExcelWorkbook -WorkbookPath $temporaryCopyPath -Visible:$Visible
                try {
                    $copyContext.Workbook.SaveAs($target.path, $target.format.fileFormat)
                }
                finally {
                    Close-ExcelWorkbook -Context $copyContext -SaveChanges:$false
                    if (Test-Path -LiteralPath $temporaryCopyPath) {
                        Remove-Item -LiteralPath $temporaryCopyPath -Force -ErrorAction SilentlyContinue
                    }
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    targetPath = [string]$target.path
                    targetFormat = [string]$target.format.format
                    compatibility = $compatibility
                    saved = $true
                }
            }
            'workbook-document-inspect' {
                $inspection = Get-ExcelWorkbookLifecycleInspection `
                    -WorkbookPath $WorkbookPath `
                    -Visible:$Visible `
                    -Backend 'auto'
                $documentInspection = Invoke-WorkbookDocumentInspection -Workbook $context.Workbook -InspectionPayload $inspection -Apply:$Apply
                if ($Apply -and -not [string]::IsNullOrWhiteSpace($TargetPath)) {
                    Ensure-ParentDirectory -Path $TargetPath
                    $context.Workbook.SaveAs([System.IO.Path]::GetFullPath($TargetPath))
                }
                elseif ($Apply) {
                    $context.Workbook.Save()
                    $saveChanges = $true
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    targetPath = if ([string]::IsNullOrWhiteSpace($TargetPath)) { $null } else { [System.IO.Path]::GetFullPath($TargetPath) }
                    inspection = $documentInspection
                }
            }
            'workbook-links' {
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    links = @(Get-WorkbookLinkInventory -Workbook $context.Workbook)
                }
            }
            'workbook-break-links' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                $linkNames = @()
                $breakAll = $true
                if ($null -ne $spec) {
                    if ($null -ne $spec.PSObject.Properties['names']) { $linkNames = @($spec.names) }
                    if ($null -ne $spec.PSObject.Properties['all']) { $breakAll = [bool]$spec.all }
                }
                elseif (@($Name).Count -gt 0) {
                    $linkNames = @($Name)
                    $breakAll = $false
                }
                $result = Invoke-WorkbookBreakLinks -Workbook $context.Workbook -Names $linkNames -All:$breakAll
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    links = $result
                }
            }
            'workbook-repoint-links' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec -or $null -eq $spec.PSObject.Properties['mappings']) {
                    throw "workbook repoint-links requires --spec-json or --spec-file with a mappings array"
                }
                $result = Invoke-WorkbookRepointLinks -Workbook $context.Workbook -Mappings @($spec.mappings)
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    links = $result
                }
            }
            'table-get' {
                if (@($Table).Count -lt 1) {
                    throw "table get requires --table"
                }
                $tables = @(Get-TableQuery -Workbook $context.Workbook)
                $item = Get-DirectWorkbookItemByName -Items $tables -Name ([string]$Table[0])
                if ($null -eq $item) {
                    throw "Table not found: $($Table[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    table = $item
                }
            }
            'table-create' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "table create requires --spec-json or --spec-file"
                }
                Ensure-DirectTableDefinition -Workbook $context.Workbook -TableSpec $spec -Mode 'create'
                $context.Workbook.Save()
                $saveChanges = $true
                $tables = @(Get-TableQuery -Workbook $context.Workbook)
                $item = Get-DirectWorkbookItemByName -Items $tables -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    table = $item
                }
            }
            'table-update' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "table update requires --spec-json or --spec-file"
                }
                Ensure-DirectTableDefinition -Workbook $context.Workbook -TableSpec $spec -Mode 'update'
                $context.Workbook.Save()
                $saveChanges = $true
                $tables = @(Get-TableQuery -Workbook $context.Workbook)
                $item = Get-DirectWorkbookItemByName -Items $tables -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    table = $item
                }
            }
            'table-delete' {
                if (@($Table).Count -lt 1) {
                    throw "table delete requires --table"
                }
                $removed = Remove-DirectTableDefinition -Workbook $context.Workbook -TableName ([string]$Table[0])
                if (-not $removed) {
                    throw "Table not found: $($Table[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    table = [string]$Table[0]
                }
            }
            'query-get' {
                if (@($QueryName).Count -lt 1) {
                    throw "query get requires --query-name"
                }
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items $payload.queries -Name ([string]$QueryName[0])
                if ($null -eq $item) {
                    throw "Power Query not found: $($QueryName[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    query = $item
                }
            }
            'query-set' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "query set requires --spec-json or --spec-file"
                }
                Ensure-PowerQueryDefinition -Workbook $context.Workbook -QuerySpec $spec
                $context.Workbook.Save()
                $saveChanges = $true
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items $payload.queries -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    query = $item
                }
            }
            'query-delete' {
                if (@($QueryName).Count -lt 1) {
                    throw "query delete requires --query-name"
                }
                $removed = Remove-WorkbookQueryDefinition -Workbook $context.Workbook -QueryName ([string]$QueryName[0])
                if (-not $removed) {
                    throw "Power Query not found: $($QueryName[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    query = [string]$QueryName[0]
                }
            }
            'query-refresh' {
                $results = @(Invoke-WorkbookPowerQueryRefresh -Workbook $context.Workbook -QueryNames $QueryName)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    results = @($results)
                }
            }
            'connection-list' {
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    connections = @($payload.connections)
                }
            }
            'connection-get' {
                if (@($Connection).Count -lt 1) {
                    throw "connection get requires --connection"
                }
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items $payload.connections -Name ([string]$Connection[0])
                if ($null -eq $item) {
                    throw "Connection not found: $($Connection[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    connection = $item
                }
            }
            'connection-update' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "connection update requires --spec-json or --spec-file"
                }
                $connectionName = if ($null -ne $spec.PSObject.Properties['name'] -and -not [string]::IsNullOrWhiteSpace([string]$spec.name)) {
                    [string]$spec.name
                }
                elseif (@($Connection).Count -gt 0) {
                    [string]$Connection[0]
                }
                else {
                    $null
                }
                if ([string]::IsNullOrWhiteSpace($connectionName)) {
                    throw "connection update requires --connection or a spec name"
                }
                $connectionObject = Find-WorkbookConnectionByName -Workbook $context.Workbook -ConnectionName $connectionName
                if ($null -eq $connectionObject) {
                    throw "Connection not found: $connectionName"
                }
                Set-WorkbookConnectionArtifact -Connection $connectionObject -ConnectionSpec $spec
                $context.Workbook.Save()
                $saveChanges = $true
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items $payload.connections -Name $connectionName
                if ($null -ne $item -and $null -ne $spec.PSObject.Properties['description']) {
                    $item.description = [string]$spec.description
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    connection = $item
                }
            }
            'connection-delete' {
                if (@($Connection).Count -lt 1) {
                    throw "connection delete requires --connection"
                }
                $connectionName = [string]$Connection[0]
                $connectionObject = Find-WorkbookConnectionByName -Workbook $context.Workbook -ConnectionName $connectionName
                if ($null -eq $connectionObject) {
                    throw "Connection not found: $connectionName"
                }
                Invoke-LateMethod -Target $connectionObject -Name 'Delete' | Out-Null
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    connection = $connectionName
                }
            }
            'chart-list' {
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    charts = @(Get-ChartQuery -Workbook $context.Workbook)
                }
            }
            'chart-get' {
                if (@($Chart).Count -lt 1) {
                    throw "chart get requires --chart"
                }
                $charts = @(Get-ChartQuery -Workbook $context.Workbook)
                $item = Get-DirectWorkbookItemByName -Items $charts -Name ([string]$Chart[0])
                if ($null -eq $item) {
                    throw "Chart not found: $($Chart[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    chart = $item
                }
            }
            'chart-create' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "chart create requires --spec-json or --spec-file"
                }
                Ensure-DirectChartDefinition -Workbook $context.Workbook -ChartSpec $spec -Mode 'create'
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-ChartQuery -Workbook $context.Workbook) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    chart = $item
                }
            }
            'chart-update' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "chart update requires --spec-json or --spec-file"
                }
                Ensure-DirectChartDefinition -Workbook $context.Workbook -ChartSpec $spec -Mode 'update'
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-ChartQuery -Workbook $context.Workbook) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    chart = $item
                }
            }
            'chart-delete' {
                if (@($Chart).Count -lt 1) {
                    throw "chart delete requires --chart"
                }
                $removed = Remove-DirectChartDefinition -Workbook $context.Workbook -ChartName ([string]$Chart[0])
                if (-not $removed) {
                    throw "Chart not found: $($Chart[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    chart = [string]$Chart[0]
                }
            }
            'shape-list' {
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    shapes = @(Get-DrawingQuery -Workbook $context.Workbook -Kind 'shapes')
                }
            }
            'shape-get' {
                if (@($Name).Count -lt 1) {
                    throw "shape get requires --name"
                }
                $item = Find-DirectDrawing -Workbook $context.Workbook -Name ([string]$Name[0]) -Kind 'shapes'
                if ($null -eq $item) {
                    throw "Shape not found: $($Name[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    shape = $item.payload
                }
            }
            'shape-create' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "shape create requires --spec-json or --spec-file"
                }
                [void](Ensure-DirectShapeDefinition -Workbook $context.Workbook -Spec $spec -Mode 'create')
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Find-DirectDrawing -Workbook $context.Workbook -Name ([string]$spec.name) -Kind 'shapes'
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    shape = $item.payload
                }
            }
            'shape-update' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "shape update requires --spec-json or --spec-file"
                }
                [void](Ensure-DirectShapeDefinition -Workbook $context.Workbook -Spec $spec -Mode 'update')
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Find-DirectDrawing -Workbook $context.Workbook -Name ([string]$spec.name) -Kind 'shapes'
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    shape = $item.payload
                }
            }
            'shape-delete' {
                if (@($Name).Count -lt 1) {
                    throw "shape delete requires --name"
                }
                $removed = Remove-DirectDrawingDefinition -Workbook $context.Workbook -Name ([string]$Name[0]) -Kind 'shapes'
                if (-not $removed) {
                    throw "Shape not found: $($Name[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    shape = [string]$Name[0]
                }
            }
            'picture-list' {
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    pictures = @(Get-DrawingQuery -Workbook $context.Workbook -Kind 'pictures')
                }
            }
            'picture-get' {
                if (@($Name).Count -lt 1) {
                    throw "picture get requires --name"
                }
                $item = Find-DirectDrawing -Workbook $context.Workbook -Name ([string]$Name[0]) -Kind 'pictures'
                if ($null -eq $item) {
                    throw "Picture not found: $($Name[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    picture = $item.payload
                }
            }
            'picture-add' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "picture add requires --spec-json or --spec-file"
                }
                [void](Ensure-DirectPictureDefinition -Workbook $context.Workbook -Spec $spec -Mode 'add')
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Find-DirectDrawing -Workbook $context.Workbook -Name ([string]$spec.name) -Kind 'pictures'
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    picture = $item.payload
                }
            }
            'picture-update' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "picture update requires --spec-json or --spec-file"
                }
                [void](Ensure-DirectPictureDefinition -Workbook $context.Workbook -Spec $spec -Mode 'update')
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Find-DirectDrawing -Workbook $context.Workbook -Name ([string]$spec.name) -Kind 'pictures'
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    picture = $item.payload
                }
            }
            'picture-delete' {
                if (@($Name).Count -lt 1) {
                    throw "picture delete requires --name"
                }
                $removed = Remove-DirectDrawingDefinition -Workbook $context.Workbook -Name ([string]$Name[0]) -Kind 'pictures'
                if (-not $removed) {
                    throw "Picture not found: $($Name[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    picture = [string]$Name[0]
                }
            }
            'control-list' {
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    controls = @(Get-DrawingQuery -Workbook $context.Workbook -Kind 'controls')
                }
            }
            'control-get' {
                if (@($Name).Count -lt 1) {
                    throw "control get requires --name"
                }
                $item = Find-DirectDrawing -Workbook $context.Workbook -Name ([string]$Name[0]) -Kind 'controls'
                if ($null -eq $item) {
                    throw "Control not found: $($Name[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    control = $item.payload
                }
            }
            'pivot-list' {
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    pivots = @(Get-PivotQuery -Workbook $context.Workbook)
                }
            }
            'pivot-get' {
                if (@($Pivot).Count -lt 1) {
                    throw "pivot get requires --pivot"
                }
                $pivots = @(Get-PivotQuery -Workbook $context.Workbook)
                $item = Get-DirectWorkbookItemByName -Items $pivots -Name ([string]$Pivot[0])
                if ($null -eq $item) {
                    throw "Pivot not found: $($Pivot[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    pivot = $item
                }
            }
            'pivot-create' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "pivot create requires --spec-json or --spec-file"
                }
                Ensure-DirectPivotDefinition -Workbook $context.Workbook -PivotSpec $spec -Mode 'create'
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-PivotQuery -Workbook $context.Workbook) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    pivot = $item
                }
            }
            'pivot-update' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "pivot update requires --spec-json or --spec-file"
                }
                Ensure-DirectPivotDefinition -Workbook $context.Workbook -PivotSpec $spec -Mode 'update'
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-PivotQuery -Workbook $context.Workbook) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    pivot = $item
                }
            }
            'pivot-delete' {
                if (@($Pivot).Count -lt 1) {
                    throw "pivot delete requires --pivot"
                }
                $removed = Remove-DirectPivotDefinition -Workbook $context.Workbook -PivotName ([string]$Pivot[0])
                if (-not $removed) {
                    throw "Pivot not found: $($Pivot[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    pivot = [string]$Pivot[0]
                }
            }
            'pivot-refresh' {
                if (@($Pivot).Count -lt 1) {
                    throw "pivot refresh requires --pivot"
                }
                $existing = Find-DirectPivotDefinition -Workbook $context.Workbook -PivotName ([string]$Pivot[0])
                if ($null -eq $existing) {
                    throw "Pivot not found: $($Pivot[0])"
                }
                try { $existing.pivotTable.PivotCache().Refresh() } catch {}
                $existing.pivotTable.RefreshTable() | Out-Null
                $item = Get-DirectWorkbookItemByName -Items @(Get-PivotQuery -Workbook $context.Workbook) -Name ([string]$Pivot[0])
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    refreshed = $true
                    pivot = $item
                }
            }
            'slicer-list' {
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    slicers = @(Get-SlicerQuery -Workbook $context.Workbook)
                }
            }
            'slicer-get' {
                if (@($Slicer).Count -lt 1) {
                    throw "slicer get requires --slicer"
                }
                $item = Get-DirectWorkbookItemByName -Items @(Get-SlicerQuery -Workbook $context.Workbook) -Name ([string]$Slicer[0])
                if ($null -eq $item) {
                    throw "Slicer not found: $($Slicer[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    slicer = $item
                }
            }
            'slicer-create' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "slicer create requires --spec-json or --spec-file"
                }
                Ensure-DirectSlicerLikeDefinition -Workbook $context.Workbook -Spec $spec -Mode 'create'
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-SlicerQuery -Workbook $context.Workbook) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    slicer = $item
                }
            }
            'slicer-update' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "slicer update requires --spec-json or --spec-file"
                }
                Ensure-DirectSlicerLikeDefinition -Workbook $context.Workbook -Spec $spec -Mode 'update'
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-SlicerQuery -Workbook $context.Workbook) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    slicer = $item
                }
            }
            'slicer-delete' {
                if (@($Slicer).Count -lt 1) {
                    throw "slicer delete requires --slicer"
                }
                $removed = Remove-DirectSlicerLikeDefinition -Workbook $context.Workbook -Name ([string]$Slicer[0])
                if (-not $removed) {
                    throw "Slicer not found: $($Slicer[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    slicer = [string]$Slicer[0]
                }
            }
            'slicer-clear' {
                if (@($Slicer).Count -lt 1) {
                    throw "slicer clear requires --slicer"
                }
                $existing = Find-DirectSlicerControlDefinition -Workbook $context.Workbook -Name ([string]$Slicer[0])
                if ($null -eq $existing) {
                    throw "Slicer not found: $($Slicer[0])"
                }
                try { Invoke-LateMethod -Target $existing.cache -Name 'ClearManualFilter' | Out-Null } catch {}
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-SlicerQuery -Workbook $context.Workbook) -Name ([string]$Slicer[0])
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    cleared = $true
                    slicer = $item
                }
            }
            'slicer-set-filter' {
                if (@($Slicer).Count -lt 1) {
                    throw "slicer set-filter requires --slicer"
                }
                $existing = Find-DirectSlicerControlDefinition -Workbook $context.Workbook -Name ([string]$Slicer[0])
                if ($null -eq $existing) {
                    throw "Slicer not found: $($Slicer[0])"
                }
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "slicer set-filter requires --spec-json or --spec-file"
                }
                Set-SlicerCacheFilterState -SlicerCache $existing.cache -Spec $spec
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-SlicerQuery -Workbook $context.Workbook) -Name ([string]$Slicer[0])
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    slicer = $item
                }
            }
            'timeline-list' {
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    timelines = @(Get-TimelineQuery -Workbook $context.Workbook)
                }
            }
            'timeline-get' {
                if (@($Timeline).Count -lt 1) {
                    throw "timeline get requires --timeline"
                }
                $item = Get-DirectWorkbookItemByName -Items @(Get-TimelineQuery -Workbook $context.Workbook) -Name ([string]$Timeline[0])
                if ($null -eq $item) {
                    throw "Timeline not found: $($Timeline[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    timeline = $item
                }
            }
            'timeline-create' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "timeline create requires --spec-json or --spec-file"
                }
                Ensure-DirectSlicerLikeDefinition -Workbook $context.Workbook -Spec $spec -Mode 'create' -Timeline
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-TimelineQuery -Workbook $context.Workbook) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    timeline = $item
                }
            }
            'timeline-update' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "timeline update requires --spec-json or --spec-file"
                }
                Ensure-DirectSlicerLikeDefinition -Workbook $context.Workbook -Spec $spec -Mode 'update' -Timeline
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-TimelineQuery -Workbook $context.Workbook) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    timeline = $item
                }
            }
            'timeline-delete' {
                if (@($Timeline).Count -lt 1) {
                    throw "timeline delete requires --timeline"
                }
                $removed = Remove-DirectSlicerLikeDefinition -Workbook $context.Workbook -Name ([string]$Timeline[0]) -Timeline
                if (-not $removed) {
                    throw "Timeline not found: $($Timeline[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    timeline = [string]$Timeline[0]
                }
            }
            'timeline-clear' {
                if (@($Timeline).Count -lt 1) {
                    throw "timeline clear requires --timeline"
                }
                $existing = Find-DirectSlicerControlDefinition -Workbook $context.Workbook -Name ([string]$Timeline[0]) -Timeline
                if ($null -eq $existing) {
                    throw "Timeline not found: $($Timeline[0])"
                }
                try { Invoke-LateMethod -Target $existing.cache -Name 'ClearManualFilter' | Out-Null } catch {}
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-TimelineQuery -Workbook $context.Workbook) -Name ([string]$Timeline[0])
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    cleared = $true
                    timeline = $item
                }
            }
            'timeline-set-range' {
                if (@($Timeline).Count -lt 1) {
                    throw "timeline set-range requires --timeline"
                }
                $existing = Find-DirectSlicerControlDefinition -Workbook $context.Workbook -Name ([string]$Timeline[0]) -Timeline
                if ($null -eq $existing) {
                    throw "Timeline not found: $($Timeline[0])"
                }
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "timeline set-range requires --spec-json or --spec-file"
                }
                Set-TimelineCacheFilterState -SlicerCache $existing.cache -Spec $spec
                $context.Workbook.Save()
                $saveChanges = $true
                $item = Get-DirectWorkbookItemByName -Items @(Get-TimelineQuery -Workbook $context.Workbook) -Name ([string]$Timeline[0])
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    timeline = $item
                }
            }
            'model-inspect' {
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    model = [pscustomobject]@{
                        modelTables = if ($null -ne $payload.PSObject.Properties['modelTables']) { @($payload.modelTables) } else { @() }
                        measures = if ($null -ne $payload.PSObject.Properties['measures']) { @($payload.measures) } else { @() }
                        relationships = if ($null -ne $payload.PSObject.Properties['relationships']) { @($payload.relationships) } else { @() }
                        hierarchies = if ($null -ne $payload.PSObject.Properties['hierarchies']) { @($payload.hierarchies) } else { @() }
                        kpis = if ($null -ne $payload.PSObject.Properties['kpis']) { @($payload.kpis) } else { @() }
                        perspectives = if ($null -ne $payload.PSObject.Properties['perspectives']) { @($payload.perspectives) } else { @() }
                    }
                }
            }
            'measure-list' {
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    measures = if ($null -ne $payload.PSObject.Properties['measures']) { @($payload.measures) } else { @() }
                }
            }
            'measure-get' {
                if (@($Name).Count -lt 1) {
                    throw "measure get requires --name"
                }
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items @($payload.measures) -Name ([string]$Name[0])
                if ($null -eq $item) {
                    throw "Model measure not found: $($Name[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    measure = $item
                }
            }
            'measure-set' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "measure set requires --spec-json or --spec-file"
                }
                if (-not (Test-WorkbookModelHasWritableTables -Workbook $context.Workbook)) {
                    return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$spec.name) -Spec $spec
                }
                [void](Ensure-WorkbookModelMeasure -Workbook $context.Workbook -MeasureSpec $spec)
                $context.Workbook.Save()
                $saveChanges = $true
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items @($payload.measures) -Name ([string]$spec.name)
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    measure = $item
                }
            }
            'measure-delete' {
                if (@($Name).Count -lt 1) {
                    throw "measure delete requires --name"
                }
                if (-not (Test-WorkbookModelHasWritableTables -Workbook $context.Workbook)) {
                    return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$Name[0]) -Spec $null
                }
                $removed = Remove-WorkbookModelMeasure -Workbook $context.Workbook -MeasureName ([string]$Name[0])
                if (-not $removed) {
                    throw "Model measure not found: $($Name[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    measure = [string]$Name[0]
                }
            }
            'relationship-list' {
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    relationships = if ($null -ne $payload.PSObject.Properties['relationships']) { @($payload.relationships) } else { @() }
                }
            }
            'relationship-get' {
                if (@($Name).Count -lt 1) {
                    throw "relationship get requires --name"
                }
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items @($payload.relationships) -Name ([string]$Name[0])
                if ($null -eq $item) {
                    $item = @($payload.relationships | Where-Object { [string]$_.id -eq [string]$Name[0] }) | Select-Object -First 1
                }
                if ($null -eq $item) {
                    throw "Model relationship not found: $($Name[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    relationship = $item
                }
            }
            'relationship-set' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "relationship set requires --spec-json or --spec-file"
                }
                $relationshipId = Get-WorkbookModelRelationshipId -ForeignKeyTable ([string]$spec.foreignKeyTable) -ForeignKeyColumn ([string]$spec.foreignKeyColumn) -PrimaryKeyTable ([string]$spec.primaryKeyTable) -PrimaryKeyColumn ([string]$spec.primaryKeyColumn)
                if (-not (Test-WorkbookModelHasWritableTables -Workbook $context.Workbook)) {
                    return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name $relationshipId -Spec $spec
                }
                [void](Ensure-WorkbookModelRelationship -Workbook $context.Workbook -RelationshipSpec $spec)
                $context.Workbook.Save()
                $saveChanges = $true
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = @($payload.relationships | Where-Object { [string]$_.id -eq $relationshipId }) | Select-Object -First 1
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    changed = $true
                    relationship = $item
                }
            }
            'relationship-delete' {
                if (@($Name).Count -lt 1) {
                    throw "relationship delete requires --name"
                }
                if (-not (Test-WorkbookModelHasWritableTables -Workbook $context.Workbook)) {
                    return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$Name[0]) -Spec $null
                }
                $removed = Remove-WorkbookModelRelationship -Workbook $context.Workbook -RelationshipId ([string]$Name[0])
                if (-not $removed) {
                    throw "Model relationship not found: $($Name[0])"
                }
                $context.Workbook.Save()
                $saveChanges = $true
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    deleted = $true
                    relationship = [string]$Name[0]
                }
            }
            'hierarchy-list' {
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    hierarchies = if ($null -ne $payload.PSObject.Properties['hierarchies']) { @($payload.hierarchies) } else { @() }
                }
            }
            'hierarchy-get' {
                if (@($Name).Count -lt 1) {
                    throw "hierarchy get requires --name"
                }
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items @($payload.hierarchies) -Name ([string]$Name[0])
                if ($null -eq $item) {
                    $item = @($payload.hierarchies | Where-Object { [string]$_.id -eq [string]$Name[0] }) | Select-Object -First 1
                }
                if ($null -eq $item) {
                    throw "Model hierarchy not found: $($Name[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    hierarchy = $item
                }
            }
            'hierarchy-set' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "hierarchy set requires --spec-json or --spec-file"
                }
                return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$spec.name) -Spec $spec
            }
            'hierarchy-delete' {
                if (@($Name).Count -lt 1) {
                    throw "hierarchy delete requires --name"
                }
                return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$Name[0]) -Spec $null
            }
            'kpi-list' {
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    kpis = if ($null -ne $payload.PSObject.Properties['kpis']) { @($payload.kpis) } else { @() }
                }
            }
            'kpi-get' {
                if (@($Name).Count -lt 1) {
                    throw "kpi get requires --name"
                }
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items @($payload.kpis) -Name ([string]$Name[0])
                if ($null -eq $item) {
                    throw "Model KPI not found: $($Name[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    kpi = $item
                }
            }
            'kpi-set' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "kpi set requires --spec-json or --spec-file"
                }
                return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$spec.name) -Spec $spec
            }
            'kpi-delete' {
                if (@($Name).Count -lt 1) {
                    throw "kpi delete requires --name"
                }
                return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$Name[0]) -Spec $null
            }
            'perspective-list' {
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    perspectives = if ($null -ne $payload.PSObject.Properties['perspectives']) { @($payload.perspectives) } else { @() }
                }
            }
            'perspective-get' {
                if (@($Name).Count -lt 1) {
                    throw "perspective get requires --name"
                }
                $payload = Get-DirectWorkbookQueryPayload -Workbook $context.Workbook
                $item = Get-DirectWorkbookItemByName -Items @($payload.perspectives) -Name ([string]$Name[0])
                if ($null -eq $item) {
                    throw "Model perspective not found: $($Name[0])"
                }
                return [pscustomobject]@{
                    command = $Command
                    backend = 'excel'
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    perspective = $item
                }
            }
            'perspective-set' {
                $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
                if ($null -eq $spec) {
                    throw "perspective set requires --spec-json or --spec-file"
                }
                return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$spec.name) -Spec $spec
            }
            'perspective-delete' {
                if (@($Name).Count -lt 1) {
                    throw "perspective delete requires --name"
                }
                return New-WorkbookModelPlatformLimitedMutation -Command $Command -WorkbookPath $WorkbookPath -Name ([string]$Name[0]) -Spec $null
            }
        }
    }
    finally {
        Close-ExcelWorkbook -Context $context -SaveChanges:$saveChanges
    }
}

function Ensure-PowerQueryDefinition {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $QuerySpec
    )

    $existing = $null
    foreach ($query in $Workbook.Queries) {
        if ([string]$query.Name -eq [string]$QuerySpec.name) {
            $existing = $query
            break
        }
    }

    if ($null -eq $existing) {
        $arguments = @([string]$QuerySpec.name, [string]$QuerySpec.formula)
        if ($null -ne $QuerySpec.PSObject.Properties['description'] -and $null -ne $QuerySpec.description) {
            $arguments += [string]$QuerySpec.description
        }
        Invoke-LateMethod -Target $Workbook.Queries -Name 'Add' -Arguments $arguments | Out-Null
        return
    }

    try {
        if ([string]$existing.Formula -ne [string]$QuerySpec.formula) {
            $existing.Formula = [string]$QuerySpec.formula
        }
    }
    catch {
        $existing.Formula = [string]$QuerySpec.formula
    }

    if ($null -ne $QuerySpec.PSObject.Properties['description'] -and $null -ne $QuerySpec.description) {
        try {
            if ([string]$existing.Description -ne [string]$QuerySpec.description) {
                $existing.Description = [string]$QuerySpec.description
            }
        }
        catch {
        }
    }
}

function Set-WorkbookConnectionArtifact {
    param(
        [Parameter(Mandatory = $true)]
        $Connection,
        [Parameter(Mandatory = $true)]
        $ConnectionSpec
    )

    try {
        if ($null -ne $ConnectionSpec.PSObject.Properties['description']) {
            [void](Try-SetProperty -Target $Connection -Name 'Description' -Value ([string]$ConnectionSpec.description))
        }
        if ($null -ne $ConnectionSpec.PSObject.Properties['oledb'] -and $null -ne $ConnectionSpec.oledb) {
            $oledb = $Connection.OLEDBConnection
            if ($null -ne $oledb) {
                foreach ($item in @(
                    @{ Name = 'BackgroundQuery'; Value = if ($null -ne $ConnectionSpec.oledb.PSObject.Properties['backgroundQuery']) { $ConnectionSpec.oledb.backgroundQuery } else { $null } },
                    @{ Name = 'RefreshOnFileOpen'; Value = if ($null -ne $ConnectionSpec.oledb.PSObject.Properties['refreshOnFileOpen']) { $ConnectionSpec.oledb.refreshOnFileOpen } else { $null } },
                    @{ Name = 'RefreshWithRefreshAll'; Value = if ($null -ne $ConnectionSpec.oledb.PSObject.Properties['refreshWithRefreshAll']) { $ConnectionSpec.oledb.refreshWithRefreshAll } else { $null } }
                )) {
                    if ($null -ne $item.Value) {
                        [void](Try-SetProperty -Target $oledb -Name $item.Name -Value ([bool]$item.Value))
                    }
                }
            }
        }
    }
    catch {
    }
}

function Ensure-PowerQueryArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        $ResolvedManifest
    )

    $artifacts = Read-PowerQueryArtifacts -ResolvedManifest $ResolvedManifest
    foreach ($query in $artifacts.queries) {
        Ensure-PowerQueryDefinition -Workbook $Workbook -QuerySpec $query
    }
    foreach ($connectionSpec in $artifacts.connections) {
        $connection = Find-WorkbookConnectionByName -Workbook $Workbook -ConnectionName ([string]$connectionSpec.name)
        if ($null -ne $connection) {
            Set-WorkbookConnectionArtifact -Connection $connection -ConnectionSpec $connectionSpec
        }
    }
    foreach ($measureSpec in @($artifacts.measures)) {
        Ensure-WorkbookModelMeasure -Workbook $Workbook -MeasureSpec $measureSpec | Out-Null
    }
    foreach ($relationshipSpec in @($artifacts.relationships)) {
        Ensure-WorkbookModelRelationship -Workbook $Workbook -RelationshipSpec $relationshipSpec | Out-Null
    }
}

function Wait-ForExcelAsyncQueries {
    param(
        $Excel,
        [object[]]$Connections = @(),
        [int]$TimeoutSeconds = 60,
        [int]$PollMilliseconds = 250
    )

    try {
        Invoke-LateMethod -Target $Excel -Name 'CalculateUntilAsyncQueriesDone' | Out-Null
    }
    catch {
    }

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $pending = $false
        foreach ($connection in @($Connections)) {
            try {
                if ($null -ne $connection.OLEDBConnection -and [bool]$connection.OLEDBConnection.Refreshing) {
                    $pending = $true
                    break
                }
            }
            catch {
            }
        }

        if (-not $pending) {
            return [pscustomobject]@{
                completed = $true
                timedOut = $false
                elapsedSeconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
            }
        }

        Start-Sleep -Milliseconds $PollMilliseconds
    }

    return [pscustomobject]@{
        completed = $false
        timedOut = $true
        elapsedSeconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
    }
}

function Invoke-WorkbookPowerQueryRefresh {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [string[]]$QueryNames = @()
    )

    $connections = @(Get-WorkbookConnectionArtifacts -Workbook $Workbook)
    $targets = @()
    if (@($QueryNames).Count -gt 0) {
        foreach ($name in @($QueryNames | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
            $connectionName = if ([string]$name -like 'Query - *') { [string]$name } else { "Query - $name" }
            $targets += @($connections | Where-Object { $_.name -eq $connectionName })
        }
    }
    else {
        $targets = @($connections | Where-Object {
            $null -ne $_.oledb -and
            $null -ne $_.oledb.connection -and
            [string]$_.oledb.connection -like 'OLEDB;Provider=Microsoft.Mashup.OleDb.1*'
        })
    }

    $results = @()
    foreach ($target in $targets) {
        $connection = Find-WorkbookConnectionByName -Workbook $Workbook -ConnectionName ([string]$target.name)
        if ($null -eq $connection) {
            $results += [pscustomobject]@{
                name = [string]$target.name
                success = $false
                error = 'Workbook connection not found.'
                elapsedSeconds = 0
            }
            continue
        }

        $started = Get-Date
        $errorText = $null
        try {
            try {
                if ($null -ne $connection.OLEDBConnection) {
                    [void](Try-SetProperty -Target $connection.OLEDBConnection -Name 'BackgroundQuery' -Value $false)
                }
            }
            catch {
            }
            Invoke-ExcelComWithRetry -Description ("Refreshing connection {0}" -f [string]$target.name) -Operation {
                Invoke-LateMethod -Target $connection -Name 'Refresh' | Out-Null
            } | Out-Null
            $wait = Wait-ForExcelAsyncQueries -Excel $Workbook.Application -Connections @($connection)
            if ($wait.timedOut) {
                $errorText = "Timed out waiting for refresh completion."
            }
        }
        catch {
            $errorText = $_.Exception.Message
        }

        $results += [pscustomobject]@{
            name = [string]$target.name
            success = [string]::IsNullOrWhiteSpace($errorText)
            error = $errorText
            elapsedSeconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 3)
            completed = [string]::IsNullOrWhiteSpace($errorText)
        }
    }

    return @($results)
}

function Get-VbaProjectInfo {
    param($Workbook)

    $components = @()
    $references = @()

    try {
        $project = Get-LateProperty -Target $Workbook -Name "VBProject"
        $vbComponents = Get-LateProperty -Target $project -Name "VBComponents"
        foreach ($component in $vbComponents) {
            $componentName = [string](Get-LateProperty -Target $component -Name "Name")
            $componentType = [int](Get-LateProperty -Target $component -Name "Type")
            $componentKind = Get-VbComponentTypeName -Component $component
            $codeModule = $null
            $lineCount = 0
            try {
                $codeModule = Get-LateProperty -Target $component -Name "CodeModule"
                $lineCount = [int](Get-LateProperty -Target $codeModule -Name "CountOfLines")
            }
            catch {
            }
            $components += [pscustomobject]@{
                name = $componentName
                type = $componentType
                kind = $componentKind
                lineCount = $lineCount
            }
        }

        $refs = Get-LateProperty -Target $project -Name "References"
        foreach ($reference in $refs) {
            $references += [pscustomobject]@{
                name = [string](Get-LateProperty -Target $reference -Name "Name")
                description = [string](Get-LateProperty -Target $reference -Name "Description")
                guid = [string](Get-LateProperty -Target $reference -Name "Guid")
                major = [int](Get-LateProperty -Target $reference -Name "Major")
                minor = [int](Get-LateProperty -Target $reference -Name "Minor")
                fullPath = [string](Get-LateProperty -Target $reference -Name "FullPath")
                builtIn = [bool](Get-LateProperty -Target $reference -Name "BuiltIn")
                isBroken = [bool](Get-LateProperty -Target $reference -Name "IsBroken")
            }
        }
    }
    catch {
        return [pscustomobject]@{
            accessible = $false
            error = $_.Exception.Message
            components = @()
            references = @()
        }
    }

    return [pscustomobject]@{
        accessible = $true
        error = $null
        components = @($components | Sort-Object name)
        references = @($references | Sort-Object name)
    }
}

function ConvertTo-AutomationSafeName {
    param(
        [AllowNull()]
        [string]$Value,
        [string]$Fallback = 'ExcelFoundryAutomation'
    )

    $candidate = if ([string]::IsNullOrWhiteSpace($Value)) { $Fallback } else { $Value }
    $clean = ($candidate -replace '[^A-Za-z0-9_]+', '_').Trim('_')
    if ([string]::IsNullOrWhiteSpace($clean)) {
        $clean = $Fallback
    }
    if ($clean -match '^[0-9]') {
        $clean = "A_$clean"
    }
    return $clean
}

function Get-ExcelAutomationSpec {
    param(
        [string]$AutomationType,
        [string]$SpecJson,
        [string]$SpecFile
    )

    $spec = [pscustomobject]@{}
    if (-not [string]::IsNullOrWhiteSpace($SpecJson)) {
        $spec = ConvertFrom-JsonCompat -Json $SpecJson
    }
    elseif (-not [string]::IsNullOrWhiteSpace($SpecFile)) {
        $spec = ConvertFrom-JsonCompat -Json (Get-Content -Raw -LiteralPath $SpecFile)
    }

    $operations = @()
    if ($null -ne $spec.PSObject.Properties['operations']) {
        $operations = @($spec.operations | ForEach-Object { [string]$_ })
    }

    return [pscustomobject]@{
        automationType = $AutomationType
        name = if ($null -ne $spec.PSObject.Properties['name'] -and -not [string]::IsNullOrWhiteSpace([string]$spec.name)) { [string]$spec.name } else { 'Excel Foundry Automation' }
        description = if ($null -ne $spec.PSObject.Properties['description']) { [string]$spec.description } else { '' }
        operations = @($operations)
        sheets = if ($null -ne $spec.PSObject.Properties['sheets']) { @($spec.sheets) } else { @() }
        outputPath = if ($null -ne $spec.PSObject.Properties['outputPath']) { [string]$spec.outputPath } else { $null }
        raw = $spec
    }
}

function Get-ExcelAutomationOperationCatalog {
    return @{
        'refresh-all' = @{
            label = 'Refresh All'
            vba = @(
                '    workbook.RefreshAll',
                '    statusLog = statusLog & "RefreshAll requested." & vbCrLf'
            )
            officeScript = @(
                '  workbook.refreshAllDataConnections();',
                '  workbook.refreshAllPivotTables();',
                '  log.push("Requested refresh of workbook connections and pivots.");'
            )
            excelJs = @(
                '    // TODO: refresh workbook connections and pivots with host-specific APIs if your deployment allows it.',
                '    console.log("Refresh-all scaffold emitted.");'
            )
        }
        'recalc-full' = @{
            label = 'Full Recalculation'
            vba = @(
                '    Application.CalculateFullRebuild',
                '    statusLog = statusLog & "CalculateFullRebuild requested." & vbCrLf'
            )
            officeScript = @(
                '  workbook.getApplication().calculate(ExcelScript.CalculationType.fullRebuild);',
                '  log.push("Requested full workbook recalculation.");'
            )
            excelJs = @(
                '    application.calculate(Excel.CalculationType.fullRebuild);',
                '    console.log("Requested full workbook recalculation.");'
            )
        }
        'update-pivots' = @{
            label = 'Refresh PivotTables'
            vba = @(
                '    Dim ws As Worksheet',
                '    Dim pivotTable As PivotTable',
                '    For Each ws In workbook.Worksheets',
                '        For Each pivotTable In ws.PivotTables',
                '            pivotTable.RefreshTable',
                '        Next pivotTable',
                '    Next ws',
                '    statusLog = statusLog & "PivotTables refreshed where present." & vbCrLf'
            )
            officeScript = @(
                '  workbook.refreshAllPivotTables();',
                '  log.push("Requested PivotTable refresh.");'
            )
            excelJs = @(
                '    // TODO: add explicit PivotTable refresh calls where your add-in host exposes them.',
                '    console.log("Pivot refresh scaffold emitted.");'
            )
        }
        'export-pdf' = @{
            label = 'Export PDF'
            vba = @(
                '    Dim pdfPath As String',
                '    pdfPath = workbook.Path & Application.PathSeparator & workbook.Name & ".pdf"',
                '    workbook.ExportAsFixedFormat 0, pdfPath',
                '    statusLog = statusLog & "Exported PDF to " & pdfPath & vbCrLf'
            )
            officeScript = @(
                '  log.push("PDF export is not available from Office Scripts alone; hand off export to Power Automate or desktop Excel.");'
            )
            excelJs = @(
                '    console.log("PDF export requires host-specific integration outside the core Excel JS runtime.");'
            )
            warnings = @('PDF export is desktop-Excel-oriented for VBA and requires external orchestration for Office Scripts and Excel JS.')
        }
        'save-copy' = @{
            label = 'Save Copy'
            vba = @(
                '    Dim copyPath As String',
                '    copyPath = workbook.Path & Application.PathSeparator & workbook.Name & ".copy"',
                '    workbook.SaveCopyAs copyPath',
                '    statusLog = statusLog & "Saved workbook copy to " & copyPath & vbCrLf'
            )
            officeScript = @(
                '  log.push("Workbook file-system save-copy is not directly available in Office Scripts.");'
            )
            excelJs = @(
                '    console.log("Save-copy behavior belongs in host storage logic, not the core Excel JS request context.");'
            )
            warnings = @('Save-copy is a desktop-file-system behavior. Office Scripts and Excel JS scaffolds emit a handoff note instead of a direct save.')
        }
    }
}

function Get-ExcelAutomationTargetCatalog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath
    )

    $extension = [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant()
    $macroContainer = $extension -in @('.xlsm', '.xlsb', '.xlam', '.xltm', '.xls')

    return @(
        [pscustomobject]@{
            type = 'vba'
            available = $true
            runtime = 'desktop-excel'
            recommended = $macroContainer
            limitations = @(
                'VBA does not run in Excel for the web.',
                'Macro security and Trust Center settings still govern execution.'
            )
        },
        [pscustomobject]@{
            type = 'office-script'
            available = $true
            runtime = 'excel-web-m365'
            recommended = $false
            limitations = @(
                'Office Scripts do not execute VBA.',
                'File-system and desktop export tasks typically require Power Automate or another host integration.'
            )
        },
        [pscustomobject]@{
            type = 'excel-js-api'
            available = $true
            runtime = 'office-addin'
            recommended = $false
            limitations = @(
                'Excel JS code runs inside an Office Add-in host, not inside workbook content.',
                'Host-specific storage and export flows still need outer application logic.'
            )
        },
        [pscustomobject]@{
            type = 'office-addin'
            available = $true
            runtime = 'office-addin'
            recommended = $false
            limitations = @(
                'Office Add-ins are separate solutions with their own manifest and hosting lifecycle.',
                'Add-in deployment and authentication are external to workbook sync.'
            )
        },
        [pscustomobject]@{
            type = 'artifact-workbook'
            available = $true
            runtime = 'codex-artifact-tool'
            recommended = $false
            limitations = @(
                'Artifact authoring is best for polished new .xlsx files and previews.',
                'Use package or desktop engines for fidelity-preserving mutation of existing workbooks.'
            )
        }
    )
}

function Get-ExcelAutomationInspection {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [ValidateSet('auto', 'excel', 'package')]
        [string]$Backend = 'auto',
        [switch]$Visible
    )

    $inspection = Get-ExcelWorkbookLifecycleInspection -WorkbookPath $WorkbookPath -Visible:$Visible -Backend $Backend
    $query = Get-ExcelWorkbookQuery -WorkbookPath $WorkbookPath -Surface @('vba', 'project', 'references') -Visible:$Visible -Backend $Backend
    $project = if ($null -ne $query.PSObject.Properties['project']) { $query.project } else { $null }
    $components = if ($null -ne $query.PSObject.Properties['vba']) { @($query.vba) } else { @() }
    $references = if ($null -ne $query.PSObject.Properties['references']) { @($query.references) } else { @() }
    $targets = Get-ExcelAutomationTargetCatalog -WorkbookPath $WorkbookPath

    return [pscustomobject]@{
        command = 'automation-inspect'
        workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
        backend = [string]$query.backend
        workbook = [pscustomobject]@{
            name = [string]$inspection.workbook.name
            format = [string]$inspection.workbook.format
            packageReadable = [bool]$inspection.workbook.packageReadable
            hasVbaProject = [bool]$inspection.workbook.hasVbaProject
            hasExternalLinks = [bool]$inspection.workbook.hasExternalLinks
        }
        automation = [pscustomobject]@{
            targets = @($targets)
            project = if ($null -ne $project) { $project } else {
                [pscustomobject]@{
                    accessible = $false
                    error = 'Live VBA inspection was unavailable; check backend warnings and host capabilities.'
                    componentCount = 0
                    referenceCount = 0
                }
            }
            components = @($components)
            references = @($references)
            warnings = @($inspection.warnings) + @($query.warnings)
            unsupported = if ($null -ne $query.PSObject.Properties['unsupported']) { @($query.unsupported) } else { @() }
        }
        capabilities = if ($null -ne $query.PSObject.Properties['capabilities']) { $query.capabilities } else { $inspection.capabilities }
    }
}

function New-ExcelAutomationArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('vba', 'office-script', 'excel-js-api', 'office-addin', 'artifact-workbook')]
        [string]$AutomationType,
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [string]$WorkbookPath,
        [string]$SpecJson,
        [string]$SpecFile
    )

    $spec = Get-ExcelAutomationSpec -AutomationType $AutomationType -SpecJson $SpecJson -SpecFile $SpecFile
    $catalog = Get-ExcelAutomationOperationCatalog
    $operations = @($spec.operations | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim().ToLowerInvariant() })
    $warnings = New-Object System.Collections.Generic.List[string]
    $recognized = New-Object System.Collections.Generic.List[string]
    $unsupportedOperations = New-Object System.Collections.Generic.List[string]

    foreach ($operation in $operations) {
        if ($catalog.ContainsKey($operation)) {
            $recognized.Add($operation) | Out-Null
            if ($catalog[$operation].ContainsKey('warnings')) {
                foreach ($warning in @($catalog[$operation]['warnings'])) {
                    if (-not [string]::IsNullOrWhiteSpace([string]$warning)) {
                        $warnings.Add([string]$warning) | Out-Null
                    }
                }
            }
        }
        else {
            $unsupportedOperations.Add($operation) | Out-Null
            $warnings.Add("Unsupported automation operation '$operation' was left as a comment placeholder.") | Out-Null
        }
    }

    $workbookComment = if ([string]::IsNullOrWhiteSpace($WorkbookPath)) { 'No workbook path supplied.' } else { "Workbook context: $([System.IO.Path]::GetFullPath($WorkbookPath))" }
    $safeName = ConvertTo-AutomationSafeName -Value $spec.name
    $writtenFiles = New-Object System.Collections.Generic.List[string]

    if ($AutomationType -eq 'vba') {
        $moduleName = ConvertTo-AutomationSafeName -Value $spec.name -Fallback 'ExcelFoundryModule'
        $procedureLines = New-Object System.Collections.Generic.List[string]
        foreach ($operation in $operations) {
            if ($catalog.ContainsKey($operation)) {
                foreach ($line in @($catalog[$operation].vba)) {
                    $procedureLines.Add([string]$line) | Out-Null
                }
            }
            else {
                $procedureLines.Add(("    ' TODO: implement unsupported operation: {0}" -f $operation)) | Out-Null
            }
        }
        if ($procedureLines.Count -eq 0) {
            $procedureLines.Add("    ' TODO: add workbook automation steps.") | Out-Null
        }
        $content = @(
            'Attribute VB_Name = "' + $moduleName + '"',
            'Option Explicit',
            '',
            "' Generated by Excel Foundry",
            "' " + $workbookComment,
            '',
            'Public Sub RunExcelFoundryAutomation()',
            '    On Error GoTo CleanFail',
            '    Dim workbook As Workbook',
            '    Dim statusLog As String',
            '    Set workbook = ThisWorkbook'
        ) + $procedureLines.ToArray() + @(
            '    Debug.Print statusLog',
            '    Exit Sub',
            'CleanFail:',
            '    Err.Raise Err.Number, "RunExcelFoundryAutomation", Err.Description',
            'End Sub'
        )
        Write-TextFile -Path $TargetPath -Value (($content -join "`n") + "`n")
        $writtenFiles.Add([System.IO.Path]::GetFullPath($TargetPath)) | Out-Null
    }
    elseif ($AutomationType -eq 'artifact-workbook') {
        $sheetArrayLiteral = '["Sheet1"]'
        if ($null -ne $spec.PSObject.Properties['sheets'] -and @($spec.sheets).Count -gt 0) {
            $sheetArrayLiteral = (@($spec.sheets) | ConvertTo-Json -Compress)
        }
        $outputPath = if ($null -ne $spec.PSObject.Properties['outputPath'] -and -not [string]::IsNullOrWhiteSpace([string]$spec.outputPath)) {
            [string]$spec.outputPath
        }
        elseif (-not [string]::IsNullOrWhiteSpace($WorkbookPath)) {
            [System.IO.Path]::GetFullPath($WorkbookPath)
        }
        else {
            'output.xlsx'
        }
        $outputLiteral = $outputPath | ConvertTo-Json -Compress
        $content = @(
            'import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";',
            '',
            '// Generated by Excel Foundry. Run with Node in a Codex runtime that provides @oai/artifact-tool.',
            ('const outputPath = ' + $outputLiteral + ';'),
            ('const sheetNames = ' + $sheetArrayLiteral + ';'),
            'const workbook = Workbook.create();',
            'for (const sheetName of sheetNames) {',
            '  const sheet = workbook.worksheets.add(String(sheetName).slice(0, 31) || "Sheet1");',
            '  sheet.getRange("A1").values = [[sheet.name]];',
            '  sheet.getRange("A1").format = { font: { bold: true, color: "#FFFFFF" }, fill: "#1F4E78" };',
            '  sheet.getRange("A1").format.autofitColumns();',
            '}',
            'const xlsx = await SpreadsheetFile.exportXlsx(workbook);',
            'await xlsx.save(outputPath);',
            'console.log(JSON.stringify({ command: "artifact-workbook", outputPath, sheets: sheetNames }, null, 2));'
        )
        Write-TextFile -Path $TargetPath -Value (($content -join "`n") + "`n")
        $writtenFiles.Add([System.IO.Path]::GetFullPath($TargetPath)) | Out-Null
        $warnings.Add("artifact-workbook generation uses the Codex spreadsheet runtime and is intended for polished new workbook authoring, not fidelity-preserving mutation of existing workbooks.") | Out-Null
    }
    elseif ($AutomationType -eq 'office-script') {
        $bodyLines = New-Object System.Collections.Generic.List[string]
        foreach ($operation in $operations) {
            if ($catalog.ContainsKey($operation)) {
                foreach ($line in @($catalog[$operation].officeScript)) {
                    $bodyLines.Add([string]$line) | Out-Null
                }
            }
            else {
                $bodyLines.Add(("  log.push(""TODO: implement unsupported operation: {0}"");" -f $operation)) | Out-Null
            }
        }
        if ($bodyLines.Count -eq 0) {
            $bodyLines.Add('  log.push("TODO: add Office Script automation steps.");') | Out-Null
        }
        $content = @(
            '// Generated by Excel Foundry',
            '// ' + $workbookComment,
            "function main(workbook: ExcelScript.Workbook) {",
            '  const log: string[] = [];'
        ) + $bodyLines.ToArray() + @(
            '  return {',
            '    name: "' + $safeName + '",',
            '    log',
            '  };',
            '}'
        )
        Write-TextFile -Path $TargetPath -Value (($content -join "`n") + "`n")
        $writtenFiles.Add([System.IO.Path]::GetFullPath($TargetPath)) | Out-Null
    }
    elseif ($AutomationType -eq 'excel-js-api') {
        $bodyLines = New-Object System.Collections.Generic.List[string]
        foreach ($operation in $operations) {
            if ($catalog.ContainsKey($operation)) {
                foreach ($line in @($catalog[$operation].excelJs)) {
                    $bodyLines.Add([string]$line) | Out-Null
                }
            }
            else {
                $bodyLines.Add(("    console.log(""TODO: implement unsupported operation: {0}"");" -f $operation)) | Out-Null
            }
        }
        if ($bodyLines.Count -eq 0) {
            $bodyLines.Add('    console.log("TODO: add Excel JS automation steps.");') | Out-Null
        }
        $content = @(
            '// Generated by Excel Foundry',
            '// ' + $workbookComment,
            'export async function runExcelFoundryAutomation(): Promise<void> {',
            '  await Excel.run(async (context) => {',
            '    const workbook = context.workbook;',
            '    const application = context.application;'
        ) + $bodyLines.ToArray() + @(
            '    await context.sync();',
            '  });',
            '}'
        )
        Write-TextFile -Path $TargetPath -Value (($content -join "`n") + "`n")
        $writtenFiles.Add([System.IO.Path]::GetFullPath($TargetPath)) | Out-Null
    }
    else {
        $root = [System.IO.Path]::GetFullPath($TargetPath)
        Ensure-ParentDirectory -Path (Join-Path $root 'taskpane.ts')
        $manifestPath = Join-Path $root 'manifest.xml'
        $htmlPath = Join-Path $root 'taskpane.html'
        $scriptPath = Join-Path $root 'taskpane.ts'
        $manifestId = [System.Guid]::NewGuid().ToString()
        $manifestXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="TaskPaneApp">
  <Id>$manifestId</Id>
  <Version>1.0.0.0</Version>
  <ProviderName>Excel Foundry</ProviderName>
  <DefaultLocale>en-US</DefaultLocale>
  <DisplayName DefaultValue="$($spec.name)"/>
  <Description DefaultValue="Generated Office Add-in scaffold from Excel Foundry."/>
  <Hosts>
    <Host Name="Workbook"/>
  </Hosts>
  <DefaultSettings>
    <SourceLocation DefaultValue="https://localhost/taskpane.html"/>
  </DefaultSettings>
  <Permissions>ReadWriteDocument</Permissions>
</OfficeApp>
"@
        $html = @(
            '<!DOCTYPE html>',
            '<html lang="en">',
            '<head>',
            '  <meta charset="utf-8" />',
            '  <title>Excel Foundry Add-in</title>',
            '</head>',
            '<body>',
            '  <main>',
            '    <h1>' + $spec.name + '</h1>',
            '    <p>Generated by Excel Foundry.</p>',
            '  </main>',
            '  <script type="module" src="./taskpane.ts"></script>',
            '</body>',
            '</html>'
        ) -join "`n"
        $taskpane = @(
            '// Generated by Excel Foundry',
            '// ' + $workbookComment,
            'import { runExcelFoundryAutomation } from "./automation";',
            '',
            'void runExcelFoundryAutomation();'
        ) -join "`n"
        $automationScriptPath = Join-Path $root 'automation.ts'
        $automationScript = @(
            '// Generated by Excel Foundry',
            '// Office Add-in automation entrypoint',
            'export async function runExcelFoundryAutomation(): Promise<void> {',
            '  await Excel.run(async (context) => {',
            '    const workbook = context.workbook;',
            '    const application = context.application;'
        )
        foreach ($operation in $operations) {
            if ($catalog.ContainsKey($operation)) {
                foreach ($line in @($catalog[$operation].excelJs)) {
                    $automationScript += [string]$line
                }
            }
            else {
                $automationScript += ("    console.log(""TODO: implement unsupported operation: {0}"");" -f $operation)
            }
        }
        if (@($operations).Count -eq 0) {
            $automationScript += '    console.log("TODO: add Office Add-in automation steps.");'
        }
        $automationScript += @(
            '    await context.sync();',
            '  });',
            '}'
        )
        Write-TextFile -Path $manifestPath -Value $manifestXml
        Write-TextFile -Path $htmlPath -Value ($html + "`n")
        Write-TextFile -Path $scriptPath -Value ($taskpane + "`n")
        Write-TextFile -Path $automationScriptPath -Value (($automationScript -join "`n") + "`n")
        $writtenFiles.Add($manifestPath) | Out-Null
        $writtenFiles.Add($htmlPath) | Out-Null
        $writtenFiles.Add($scriptPath) | Out-Null
        $writtenFiles.Add($automationScriptPath) | Out-Null
    }

    return [pscustomobject]@{
        command = 'automation-generate'
        automationType = $AutomationType
        workbookPath = if ([string]::IsNullOrWhiteSpace($WorkbookPath)) { $null } else { [System.IO.Path]::GetFullPath($WorkbookPath) }
        targetPath = [System.IO.Path]::GetFullPath($TargetPath)
        spec = $spec
        operations = @($recognized.ToArray())
        unsupportedOperations = @($unsupportedOperations.ToArray())
        warnings = @($warnings.ToArray())
        files = @($writtenFiles.ToArray())
    }
}

function Invoke-WorkbookAutomationRun {
    param(
        $Workbook,
        [string]$WorkbookPath,
        [string]$AutomationType,
        [string]$TargetPath,
        [string]$SpecJson,
        [string]$SpecFile
    )

    $normalizedType = if ([string]::IsNullOrWhiteSpace($AutomationType)) { 'vba' } else { $AutomationType.Trim().ToLowerInvariant() }
    if ($normalizedType -ne 'vba') {
        $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
        if ($null -eq $spec) {
            $spec = [pscustomobject]@{}
        }
        $runnerCommand = if ($null -ne $spec.PSObject.Properties['runnerCommand']) { [string]$spec.runnerCommand } else { $null }
        $platformLimits = switch ($normalizedType) {
            'office-script' { @('Office Scripts execute in Excel on the web or Microsoft 365 automation surfaces, not through local desktop COM.') }
            'excel-js-api' { @('Excel JS API execution requires an Office Add-in host or test harness.') }
            'office-addin' { @('Office Add-ins require a sideloaded add-in host and browser/runtime harness.') }
            'artifact-workbook' { @('Artifact workbook scripts execute in a Node runtime with @oai/artifact-tool available.') }
            default { @('Unknown automation runtime; provide runnerCommand in the spec to execute externally.') }
        }
        if (-not [string]::IsNullOrWhiteSpace($runnerCommand)) {
            return [pscustomobject]@{
                command = 'automation-run'
                automationType = $normalizedType
                workbookPath = if ([string]::IsNullOrWhiteSpace($WorkbookPath)) { $null } else { [System.IO.Path]::GetFullPath($WorkbookPath) }
                status = 'runner-required'
                runnerCommand = $runnerCommand
                targetPath = if ([string]::IsNullOrWhiteSpace($TargetPath)) { $null } else { [System.IO.Path]::GetFullPath($TargetPath) }
                platformLimits = @($platformLimits)
                message = 'External runner execution is intentionally explicit; run the returned command in the appropriate Microsoft/Codex host.'
            }
        }
        return [pscustomobject]@{
            command = 'automation-run'
            automationType = $normalizedType
            workbookPath = if ([string]::IsNullOrWhiteSpace($WorkbookPath)) { $null } else { [System.IO.Path]::GetFullPath($WorkbookPath) }
            status = 'runner-plan'
            canRunLocally = $false
            targetPath = if ([string]::IsNullOrWhiteSpace($TargetPath)) { $null } else { [System.IO.Path]::GetFullPath($TargetPath) }
            platformLimits = @($platformLimits)
            message = 'Generate the automation artifact, then execute it in the listed host or provide runnerCommand in the spec.'
        }
    }

    $spec = Read-JsonSpecValue -SpecJson $SpecJson -SpecFile $SpecFile
    if ($null -eq $spec) {
        $spec = [pscustomobject]@{}
    }

    $macroName = if ($null -ne $spec.PSObject.Properties['macroName'] -and -not [string]::IsNullOrWhiteSpace([string]$spec.macroName)) {
        [string]$spec.macroName
    } else {
        'RunExcelFoundryAutomation'
    }
    $componentName = if ($null -ne $spec.PSObject.Properties['componentName'] -and -not [string]::IsNullOrWhiteSpace([string]$spec.componentName)) {
        [string]$spec.componentName
    } else {
        ConvertTo-AutomationSafeName -Value $macroName -Fallback 'ExcelFoundryAutomation'
    }
    $persistComponent = ($null -ne $spec.PSObject.Properties['persistComponent'] -and [bool]$spec.persistComponent)
    $modulePath = $null
    $generatedModulePath = $null
    $componentImported = $false
    $componentRemoved = $false
    $runPayload = $null

    try {
        if (-not [string]::IsNullOrWhiteSpace($TargetPath)) {
            $modulePath = [System.IO.Path]::GetFullPath($TargetPath)
        }
        elseif ($null -ne $spec.PSObject.Properties['sourcePath'] -and -not [string]::IsNullOrWhiteSpace([string]$spec.sourcePath)) {
            $modulePath = [System.IO.Path]::GetFullPath([string]$spec.sourcePath)
        }
        elseif ($null -ne $spec.PSObject.Properties['operations'] -and @($spec.operations).Count -gt 0) {
            $generatedModulePath = Join-Path ([System.IO.Path]::GetTempPath()) ((ConvertTo-AutomationSafeName -Value $componentName -Fallback 'ExcelFoundryAutomation') + '.bas')
            [void](New-ExcelAutomationArtifacts -AutomationType 'vba' -TargetPath $generatedModulePath -WorkbookPath $WorkbookPath -SpecJson ($spec | ConvertTo-Json -Depth 100 -Compress))
            $modulePath = $generatedModulePath
        }

        if (-not [string]::IsNullOrWhiteSpace($modulePath)) {
            Set-VbaComponentArtifact -Workbook $Workbook -ComponentName $componentName -SourcePath $modulePath
            $componentImported = $true
        }

        $runResult = $Workbook.Application.Run($macroName)

        $runPayload = [pscustomobject]@{
            command = 'automation-run'
            automationType = $normalizedType
            workbookPath = if ([string]::IsNullOrWhiteSpace($WorkbookPath)) { $null } else { [System.IO.Path]::GetFullPath($WorkbookPath) }
            macroName = $macroName
            componentName = $componentName
            componentImported = $componentImported
            componentRemoved = $false
            modulePath = $modulePath
            result = $runResult
            persistedComponent = $persistComponent
        }
        return $runPayload
    }
    finally {
        if ($componentImported -and -not $persistComponent) {
            try {
                Remove-VbaComponentIfImportable -Workbook $Workbook -ComponentName $componentName
                $componentRemoved = $true
                if ($null -ne $runPayload) {
                    $runPayload.componentRemoved = $true
                }
            }
            catch {
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($generatedModulePath) -and (Test-Path -LiteralPath $generatedModulePath)) {
            Remove-Item -LiteralPath $generatedModulePath -Force
        }
    }
}

function Invoke-ExcelAutomationCommand {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('automation-inspect', 'automation-generate', 'automation-run')]
        [string]$Command,
        [string]$WorkbookPath,
        [string]$TargetPath,
        [string]$AutomationType,
        [string]$SpecJson,
        [string]$SpecFile,
        [ValidateSet('auto', 'excel', 'package')]
        [string]$Backend = 'auto',
        [switch]$Visible
    )

    switch ($Command) {
        'automation-inspect' {
            return Get-ExcelAutomationInspection -WorkbookPath $WorkbookPath -Backend $Backend -Visible:$Visible
        }
        'automation-generate' {
            return New-ExcelAutomationArtifacts -AutomationType $AutomationType -TargetPath $TargetPath -WorkbookPath $WorkbookPath -SpecJson $SpecJson -SpecFile $SpecFile
        }
        'automation-run' {
            $normalizedRunType = if ([string]::IsNullOrWhiteSpace($AutomationType)) { 'vba' } else { $AutomationType.Trim().ToLowerInvariant() }
            if ($normalizedRunType -eq 'vba' -and [string]::IsNullOrWhiteSpace($WorkbookPath)) {
                throw "VBA automation run requires --workbook-path"
            }
            if ($normalizedRunType -ne 'vba') {
                return Invoke-WorkbookAutomationRun -Workbook $null -WorkbookPath $WorkbookPath -AutomationType $AutomationType -TargetPath $TargetPath -SpecJson $SpecJson -SpecFile $SpecFile
            }
            $context = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible
            $saveChanges = $true
            try {
                return Invoke-WorkbookAutomationRun -Workbook $context.Workbook -WorkbookPath $WorkbookPath -AutomationType $AutomationType -TargetPath $TargetPath -SpecJson $SpecJson -SpecFile $SpecFile
            }
            finally {
                Close-ExcelWorkbook -Context $context -SaveChanges:$saveChanges
            }
        }
    }
}

function Get-TableQuery {
    param($Workbook)

    $tables = @()
    foreach ($worksheet in $Workbook.Worksheets) {
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
                    $row = @()
                    for ($c = 1; $c -le $colCount; $c++) {
                        $row += $listObject.DataBodyRange.Cells.Item($r, $c).Value2
                    }
                    $rows += ,$row
                }
            }

            $tables += [pscustomobject]@{
                sheet = [string]$worksheet.Name
                name = [string]$listObject.Name
                topLeft = [string]$listObject.Range.Cells.Item(1, 1).Address($false, $false)
                headers = $headers
                rows = $rows
            }
        }
    }
    return @($tables | Sort-Object sheet, name)
}

function Get-NameQuery {
    param($Workbook)

    $definitions = @()
    foreach ($existingName in $Workbook.Names) {
        $nameText = [string]$existingName.Name
        $definitions += [pscustomobject]@{
            name = $nameText
            refersTo = [string]$existingName.RefersTo
            builtIn = $nameText.StartsWith("_xlnm.", [System.StringComparison]::OrdinalIgnoreCase) -or
                $nameText.StartsWith("_xlfn.", [System.StringComparison]::OrdinalIgnoreCase) -or
                $nameText.StartsWith("_xlpm.", [System.StringComparison]::OrdinalIgnoreCase)
        }
    }
    return @($definitions | Sort-Object name)
}

function Get-CfTypeName {
    param($FormatCondition)

    try {
        $rawType = [int]$FormatCondition.Type
    }
    catch {
        return "unknown"
    }

    switch ($rawType) {
        1 { return "cell-value" }
        2 { return "expression" }
        3 { return "color-scale" }
        4 { return "data-bar" }
        5 { return "top10" }
        6 { return "icon-set" }
        8 { return "unique-values" }
        12 { return "above-average" }
        default { return "type-$rawType" }
    }
}

function Test-CfSupported {
    param($TypeName)

    return $TypeName -in @(
        "cell-value",
        "expression",
        "color-scale",
        "data-bar",
        "top10",
        "icon-set",
        "unique-values",
        "above-average"
    )
}

function Get-ConditionalFormattingQuery {
    param($Workbook)

    $rules = @()
    foreach ($worksheet in $Workbook.Worksheets) {
        $formatConditions = $null
        try {
            $formatConditions = $worksheet.Cells.FormatConditions
        }
        catch {
            try {
                $formatConditions = $worksheet.UsedRange.FormatConditions
            }
            catch {
                $formatConditions = $null
            }
        }
        if ($null -eq $formatConditions) {
            continue
        }
        $count = 0
        try {
            $count = [int]$formatConditions.Count
        }
        catch {
            continue
        }

        for ($index = 1; $index -le $count; $index++) {
            $candidate = $formatConditions.Item($index)
            $typeName = Get-CfTypeName -FormatCondition $candidate
            $appliesTo = $null
            try {
                $appliesTo = $candidate.AppliesTo
            }
            catch {
            }

            $rule = [ordered]@{
                id = ("CF-{0}-{1:000}" -f [string]$worksheet.Name, $index)
                sheet = [string]$worksheet.Name
                type = $typeName
                supported = (Test-CfSupported -TypeName $typeName)
                priority = $null
                stopIfTrue = $null
                address = if ($null -ne $appliesTo) { [string]$appliesTo.Address() } else { $null }
                formula = $null
                format = [ordered]@{
                    interiorColor = $null
                    fontColor = $null
                    bold = $null
                }
                rawType = $null
            }

            try { $rule.rawType = [int]$candidate.Type } catch {}
            try { $rule.priority = [int]$candidate.Priority } catch {}
            try { $rule.stopIfTrue = [bool]$candidate.StopIfTrue } catch {}
            try { $rule.formula = [string]$candidate.Formula1 } catch {}
            try { $rule.format.interiorColor = Convert-BgrIntToHexColor -ColorValue $candidate.Interior.Color } catch {}
            try { $rule.format.fontColor = Convert-BgrIntToHexColor -ColorValue $candidate.Font.Color } catch {}
            try { $rule.format.bold = [bool]$candidate.Font.Bold } catch {}

            switch ($typeName) {
                "cell-value" {
                    try { $rule["operator"] = [int]$candidate.Operator } catch {}
                    try { $rule["formula2"] = [string]$candidate.Formula2 } catch {}
                }
                "unique-values" {
                    try { $rule["dupeUnique"] = [int]$candidate.DupeUnique } catch {}
                }
                "top10" {
                    try { $rule["rank"] = [int]$candidate.Rank } catch {}
                    try { $rule["percent"] = [bool]$candidate.Percent } catch {}
                    try { $rule["topBottom"] = [int]$candidate.TopBottom } catch {}
                }
                "above-average" {
                    try { $rule["aboveBelow"] = [int]$candidate.AboveBelow } catch {}
                    try { $rule["numStdDev"] = [int]$candidate.NumStdDev } catch {}
                }
                "color-scale" {
                    $criteria = @()
                    try {
                        foreach ($criterion in $candidate.ColorScaleCriteria) {
                            $criteria += [pscustomobject]@{
                                type = [int]$criterion.Type
                                value = $criterion.Value
                                formatColor = Convert-BgrIntToHexColor -ColorValue $criterion.FormatColor.Color
                            }
                        }
                    }
                    catch {
                    }
                    $rule["criteria"] = $criteria
                }
                "data-bar" {
                    try { $rule["barColor"] = Convert-BgrIntToHexColor -ColorValue $candidate.BarColor.Color } catch {}
                }
                "icon-set" {
                    try { $rule["iconSetId"] = [int]$candidate.IconSet.ID } catch {}
                    try { $rule["reverseOrder"] = [bool]$candidate.ReverseOrder } catch {}
                    try { $rule["showIconOnly"] = [bool]$candidate.ShowIconOnly } catch {}
                }
            }

            $rules += [pscustomobject]$rule
        }
    }

    return @($rules | Sort-Object sheet, priority, id)
}

function Get-FormulaQuery {
    param($Workbook)

    $formulas = @()
    foreach ($worksheet in $Workbook.Worksheets) {
        $usedRange = $null
        try {
            $usedRange = $worksheet.UsedRange
        }
        catch {
            continue
        }
        if ($null -eq $usedRange) {
            continue
        }

        $rowCount = 0
        $colCount = 0
        try { $rowCount = [int]$usedRange.Rows.Count } catch { $rowCount = 0 }
        try { $colCount = [int]$usedRange.Columns.Count } catch { $colCount = 0 }
        if ($rowCount -lt 1 -or $colCount -lt 1) {
            continue
        }

        for ($row = 1; $row -le $rowCount; $row++) {
            for ($col = 1; $col -le $colCount; $col++) {
                $cell = $usedRange.Cells.Item($row, $col)
                $hasFormula = $false
                try { $hasFormula = [bool]$cell.HasFormula } catch { $hasFormula = $false }
                if (-not $hasFormula) {
                    continue
                }

                $entry = [ordered]@{
                    sheet = [string]$worksheet.Name
                    address = $null
                    formula = $null
                    formulaR1C1 = $null
                    value = $null
                }
                try { $entry.address = [string]$cell.Address($false, $false) } catch {}
                try { $entry.formula = [string]$cell.Formula } catch {}
                try { $entry.formulaR1C1 = [string]$cell.FormulaR1C1 } catch {}
                try { $entry.value = $cell.Value2 } catch {}
                $formulas += [pscustomobject]$entry
            }
        }
    }

    return @($formulas | Sort-Object sheet, address)
}

function Get-WorkbookProtectionArtifact {
    param($Workbook)

    $workbookProtection = $null
    try {
        $workbookProtection = [pscustomobject]@{
            lockStructure = [bool]$Workbook.ProtectStructure
            lockWindows = [bool]$Workbook.ProtectWindows
            lockRevision = $null
        }
    }
    catch {
        $workbookProtection = $null
    }

    $worksheets = @()
    foreach ($worksheet in $Workbook.Worksheets) {
        $entry = [ordered]@{
            sheet = [string]$worksheet.Name
            enabled = $null
            objects = $null
            scenarios = $null
        }
        $anyValue = $false
        try { $entry.enabled = [bool]$worksheet.ProtectContents; $anyValue = $true } catch {}
        try { $entry.objects = [bool]$worksheet.ProtectDrawingObjects; $anyValue = $true } catch {}
        try { $entry.scenarios = [bool]$worksheet.ProtectScenarios; $anyValue = $true } catch {}
        if ($anyValue -and ($entry.enabled -or $entry.objects -or $entry.scenarios)) {
            $worksheets += [pscustomobject]$entry
        }
    }

    return [pscustomobject]@{
        workbook = $workbookProtection
        worksheets = @($worksheets | Sort-Object sheet)
    }
}

function Get-ChartQuery {
    param($Workbook)

    $charts = @()

    foreach ($worksheet in $Workbook.Worksheets) {
        $chartObjects = $null
        try { $chartObjects = $worksheet.ChartObjects() } catch { $chartObjects = $null }
        if ($null -eq $chartObjects) {
            continue
        }

        foreach ($chartObject in $chartObjects) {
            $chart = $null
            try { $chart = $chartObject.Chart } catch { $chart = $null }
            if ($null -eq $chart) {
                continue
            }

            $entry = [ordered]@{
                name = $null
                kind = 'embedded'
                sheet = [string]$worksheet.Name
                address = $null
                chartType = $null
                hasTitle = $null
                title = $null
                series = @()
            }

            try { $entry.name = [string]$chartObject.Name } catch {}
            try {
                $topLeft = $chartObject.TopLeftCell.Address($false, $false)
                $bottomRight = $chartObject.BottomRightCell.Address($false, $false)
                $entry.address = "{0}:{1}" -f $topLeft, $bottomRight
            } catch {}
            try { $entry.chartType = [string]$chart.ChartType } catch {}
            try { $entry.hasTitle = [bool]$chart.HasTitle } catch {}
            if ($entry.hasTitle) {
                try { $entry.title = [string]$chart.ChartTitle.Text } catch {}
            }

            $series = @()
            try {
                foreach ($item in $chart.SeriesCollection()) {
                    $seriesEntry = [ordered]@{
                        name = $null
                        formula = $null
                    }
                    try { $seriesEntry.name = [string]$item.Name } catch {}
                    try { $seriesEntry.formula = [string]$item.Formula } catch {}
                    $series += [pscustomobject]$seriesEntry
                }
            }
            catch {
            }
            $entry.series = $series
            $charts += [pscustomobject]$entry
        }
    }

    try {
        foreach ($chartSheet in $Workbook.Charts) {
            $entry = [ordered]@{
                name = $null
                kind = 'chart-sheet'
                sheet = $null
                address = $null
                chartType = $null
                hasTitle = $null
                title = $null
                series = @()
            }
            try { $entry.name = [string]$chartSheet.Name } catch {}
            try { $entry.sheet = [string]$chartSheet.Name } catch {}
            try { $entry.chartType = [string]$chartSheet.ChartType } catch {}
            try { $entry.hasTitle = [bool]$chartSheet.HasTitle } catch {}
            if ($entry.hasTitle) {
                try { $entry.title = [string]$chartSheet.ChartTitle.Text } catch {}
            }
            $series = @()
            try {
                foreach ($item in $chartSheet.SeriesCollection()) {
                    $seriesEntry = [ordered]@{
                        name = $null
                        formula = $null
                    }
                    try { $seriesEntry.name = [string]$item.Name } catch {}
                    try { $seriesEntry.formula = [string]$item.Formula } catch {}
                    $series += [pscustomobject]$seriesEntry
                }
            }
            catch {
            }
            $entry.series = $series
            $charts += [pscustomobject]$entry
        }
    }
    catch {
    }

    return @($charts | Sort-Object kind, sheet, name)
}

function Get-PivotQuery {
    param($Workbook)

    $pivots = @()
    foreach ($worksheet in $Workbook.Worksheets) {
        $pivotTables = $null
        try { $pivotTables = $worksheet.PivotTables() } catch { $pivotTables = $null }
        if ($null -eq $pivotTables) {
            continue
        }

        foreach ($pivotTable in $pivotTables) {
            $entry = [ordered]@{
                name = $null
                sheet = [string]$worksheet.Name
                topLeft = $null
                tableRange = $null
                sourceData = $null
                refreshOnFileOpen = $null
                enableRefresh = $null
                hasConnection = $null
                connectionName = $null
            }
            try { $entry.name = [string]$pivotTable.Name } catch {}
            try { $entry.topLeft = [string]$pivotTable.TableRange2.Cells.Item(1, 1).Address($false, $false) } catch {}
            try { $entry.tableRange = [string]$pivotTable.TableRange2.Address() } catch {}
            try { $entry.sourceData = [string]$pivotTable.SourceData } catch {}

            $cache = $null
            try { $cache = $pivotTable.PivotCache() } catch { $cache = $null }
            if ($null -ne $cache) {
                try { $entry.refreshOnFileOpen = [bool]$cache.RefreshOnFileOpen } catch {}
                try { $entry.enableRefresh = [bool]$cache.EnableRefresh } catch {}
                try {
                    $workbookConnection = $cache.WorkbookConnection
                    if ($null -ne $workbookConnection) {
                        $entry.hasConnection = $true
                        try { $entry.connectionName = [string]$workbookConnection.Name } catch {}
                    }
                }
                catch {
                    $entry.hasConnection = $false
                }
            }

            $pivots += [pscustomobject]$entry
        }
    }

    return @($pivots | Sort-Object sheet, name)
}

function Get-ExcelBackendCapabilities {
    param(
        [Parameter(Mandatory = $true)]
        $Context,
        $ProjectInfo
    )

    $readOnly = $null
    $powerQueryWrite = $false
    try { $readOnly = [bool]$Context.ReadOnly } catch {}
    try {
        $queries = Get-LateProperty -Target $Context.Workbook -Name 'Queries'
        if ($null -ne $queries -and -not $readOnly) {
            $powerQueryWrite = $true
        }
    }
    catch {
        $powerQueryWrite = $false
    }

    return [pscustomobject]@{
        excelCom = $true
        packageReadable = (Test-OoxmlPackageWorkbook -WorkbookPath $Context.Workbook.FullName)
        canRead = $true
        canWrite = if ($null -ne $readOnly) { -not $readOnly } else { $true }
        writeBackend = if ($null -ne $readOnly -and -not $readOnly) { 'excel-com' } else { $null }
        refreshAwait = $true
        powerQueryWrite = $powerQueryWrite
        vbaProjectAccess = if ($null -ne $ProjectInfo) { [bool]$ProjectInfo.accessible } else { $null }
        workbookReadOnly = $readOnly
        lifecycle = [pscustomobject]@{
            saveAs = $true
            convert = $true
            repair = $true
            compatibilityCheck = $true
            documentInspector = $true
        }
    }
}

function Get-PackageBackendCapabilities {
    return [pscustomobject]@{
        excelCom = $false
        packageReadable = $true
        canRead = $true
        canWrite = $false
        writeBackend = $null
        refreshAwait = $false
        powerQueryWrite = $false
        vbaProjectAccess = $false
        workbookReadOnly = $null
        lifecycle = [pscustomobject]@{
            saveAs = $false
            convert = $false
            repair = $false
            compatibilityCheck = $true
            documentInspector = $false
        }
    }
}

function Test-PackagePreferredQuery {
    param(
        [string[]]$Surface = @(),
        [bool]$PackageReadable = $false,
        [string]$Backend = 'auto'
    )

    if ($Backend -ne 'auto' -or -not $PackageReadable) {
        return $false
    }

    $normalized = @($Surface | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if (@($normalized).Count -eq 0) {
        return $false
    }

    $excelOnlySurfaces = @('vba', 'project', 'references', 'slicers', 'timelines')
    return @($normalized | Where-Object { $_ -in $excelOnlySurfaces }).Count -eq 0
}

function Get-ExcelWorkbookQuery {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Surface = @(),
        [switch]$Visible,
        [ValidateSet('auto', 'excel', 'package')]
        [string]$Backend = 'auto'
    )

    $normalizedSurface =
        @($Surface | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ } | ForEach-Object {
            switch ($_) {
                'conditional-formatting' { 'cf'; break }
                'conditional_formatting' { 'cf'; break }
                'power-query' { 'pq'; break }
                'power_query' { 'pq'; break }
                'data_validation' { 'data-validation'; break }
                'datavalidation' { 'data-validation'; break }
                default { $_ }
            }
        })
    $warnings = New-Object System.Collections.Generic.List[string]
    $stagesTried = New-Object System.Collections.Generic.List[string]
    $unsupported = New-Object System.Collections.Generic.List[object]
    $packageReadable = Test-OoxmlPackageWorkbook -WorkbookPath $WorkbookPath

    if (Test-PackagePreferredQuery -Surface $normalizedSurface -PackageReadable:$packageReadable -Backend $Backend) {
        $stagesTried.Add('package')
        $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface $normalizedSurface
        if ($null -ne $payload.PSObject.Properties['stagesTried']) {
            $payload.stagesTried = ConvertTo-ObjectArray -Value $stagesTried.ToArray()
        }
        else {
            $payload | Add-Member -NotePropertyName stagesTried -NotePropertyValue (ConvertTo-ObjectArray -Value $stagesTried.ToArray())
        }
        if ($null -eq $payload.PSObject.Properties['capabilities']) {
            $payload | Add-Member -NotePropertyName capabilities -NotePropertyValue (Get-PackageBackendCapabilities)
        }
        if ($null -eq $payload.PSObject.Properties['unsupported']) {
            $payload | Add-Member -NotePropertyName unsupported -NotePropertyValue @()
        }
        return $payload
    }

    if ($Backend -in @('auto', 'excel')) {
        $stagesTried.Add('excel')
        try {
            $context = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible -ReadOnlyIntent
            try {
                $projectInfo = $null
                $payload = [ordered]@{
                    workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    backend = 'excel'
                    sourceFormat = [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant()
                    workingPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                    normalization = 'none'
                    warnings = ConvertTo-ObjectArray -Value $warnings.ToArray()
                    stagesTried = ConvertTo-ObjectArray -Value $stagesTried.ToArray()
                }

                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'tables') {
                    $payload["tables"] = @(Get-TableQuery -Workbook $context.Workbook)
                }
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'names') {
                    $payload["names"] = @(Get-NameQuery -Workbook $context.Workbook)
                }
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'cf') {
                    $payload["cf"] = @(Get-ConditionalFormattingQuery -Workbook $context.Workbook)
                }
                if ((Test-SurfaceRequested -Surface $normalizedSurface -Name 'pq') -or
                    (Test-SurfaceRequested -Surface $normalizedSurface -Name 'connections') -or
                    (Test-SurfaceRequested -Surface $normalizedSurface -Name 'model')) {
                    $powerQueryInfo = Get-WorkbookPowerQueryArtifacts -Workbook $context.Workbook
                    if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'pq') {
                        $payload["pq"] = @($powerQueryInfo.queries)
                    }
                    if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'connections') {
                        $payload["connections"] = @($powerQueryInfo.connections)
                    }
                    if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'model') {
                        $payload["model"] = [pscustomobject]@{
                            modelTables = @($powerQueryInfo.modelTables)
                            measures = @($powerQueryInfo.measures)
                            relationships = @($powerQueryInfo.relationships)
                        }
                    }
                }
                if ((Test-SurfaceRequested -Surface $normalizedSurface -Name 'vba') -or
                    (Test-SurfaceRequested -Surface $normalizedSurface -Name 'project') -or
                    (Test-SurfaceRequested -Surface $normalizedSurface -Name 'references')) {
                    $projectInfo = Get-VbaProjectInfo -Workbook $context.Workbook
                    if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'vba') {
                        $payload["vba"] = @($projectInfo.components)
                    }
                    if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'project') {
                        $payload["project"] = [pscustomobject]@{
                            accessible = $projectInfo.accessible
                            error = $projectInfo.error
                            componentCount = @($projectInfo.components).Count
                            referenceCount = @($projectInfo.references).Count
                        }
                    }
                    if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'references') {
                        $payload["references"] = @($projectInfo.references)
                    }
                }
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'formulas') {
                    $payload["formulas"] = @(Get-FormulaQuery -Workbook $context.Workbook)
                }
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'protection') {
                    $payload["protection"] = Get-WorkbookProtectionArtifact -Workbook $context.Workbook
                }
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'charts') {
                    $payload["charts"] = @(Get-ChartQuery -Workbook $context.Workbook)
                }
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'pivots') {
                    $payload["pivots"] = @(Get-PivotQuery -Workbook $context.Workbook)
                }
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'slicers') {
                    $payload["slicers"] = @(Get-SlicerQuery -Workbook $context.Workbook)
                }
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'timelines') {
                    $payload["timelines"] = @(Get-TimelineQuery -Workbook $context.Workbook)
                }

                $packageOnlySurfaces = @()
                if (Test-SurfaceRequested -Surface $normalizedSurface -Name 'data-validation') {
                    $packageOnlySurfaces += 'data-validation'
                }
                if (@($packageOnlySurfaces).Count -gt 0) {
                    if ($packageReadable) {
                        $packagePayload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface $packageOnlySurfaces
                        if ($null -ne $packagePayload.PSObject.Properties['dataValidation']) {
                            $payload["dataValidation"] = @($packagePayload.dataValidation)
                        }
                    }
                    else {
                        foreach ($surfaceName in $packageOnlySurfaces) {
                            Add-UnsupportedSurface -List $unsupported -Surface $surfaceName -Backend 'excel' -Reason 'This surface currently requires an OOXML package-readable workbook.'
                        }
                    }
                }

                $payload["capabilities"] = Get-ExcelBackendCapabilities -Context $context -ProjectInfo $projectInfo
                $payload["unsupported"] = ConvertTo-ObjectArray -Value $unsupported.ToArray()

                return [pscustomobject]$payload
            }
            finally {
                Close-ExcelWorkbook -Context $context -SaveChanges:$false
            }
        }
        catch {
            if ($Backend -eq 'excel' -or -not $packageReadable) {
                throw
            }
            $warnings.Add("Excel backend failed; falling back to package parser: $($_.Exception.Message)")
        }
    }

    if ($Backend -in @('auto', 'package')) {
        $stagesTried.Add('package')
        $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface $normalizedSurface
        if ($warnings.Count -gt 0) {
            $payload.warnings = (ConvertTo-ObjectArray -Value $payload.warnings) + (ConvertTo-ObjectArray -Value $warnings.ToArray())
        }
        $payload.stagesTried = ConvertTo-ObjectArray -Value $stagesTried.ToArray()
        if ($null -eq $payload.PSObject.Properties['capabilities']) {
            $payload | Add-Member -NotePropertyName capabilities -NotePropertyValue (Get-PackageBackendCapabilities)
        }
        if ($null -eq $payload.PSObject.Properties['unsupported']) {
            $payload | Add-Member -NotePropertyName unsupported -NotePropertyValue @()
        }
        return $payload
    }
}

function Get-ExcelWorkbookInspection {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Surface = @(),
        [switch]$Visible,
        [ValidateSet('auto', 'excel', 'package')]
        [string]$Backend = 'auto'
    )

    $query = Get-ExcelWorkbookQuery -WorkbookPath $WorkbookPath -Surface $Surface -Visible:$Visible -Backend $Backend
    $tables = @()
    $names = @()
    $cf = @()
    $pq = @()
    $connections = @()
    $model = $null
    $sheets = @()
    $vba = @()
    $references = @()
    $project = $null
    $formulas = @()
    $dataValidation = @()
    $protection = $null
    $charts = @()
    $pivots = @()
    $slicers = @()
    $timelines = @()

    if ($null -ne $query.PSObject.Properties['sheets']) { $sheets = @($query.sheets) }
    if ($null -ne $query.PSObject.Properties['tables']) { $tables = @($query.tables) }
    if ($null -ne $query.PSObject.Properties['names']) { $names = @($query.names) }
    if ($null -ne $query.PSObject.Properties['cf']) { $cf = @($query.cf) }
    if ($null -ne $query.PSObject.Properties['pq']) { $pq = @($query.pq) }
    if ($null -ne $query.PSObject.Properties['connections']) { $connections = @($query.connections) }
    if ($null -ne $query.PSObject.Properties['model']) { $model = $query.model }
    if ($null -ne $query.PSObject.Properties['vba']) { $vba = @($query.vba) }
    if ($null -ne $query.PSObject.Properties['references']) { $references = @($query.references) }
    if ($null -ne $query.PSObject.Properties['project']) { $project = $query.project }
    if ($null -ne $query.PSObject.Properties['formulas']) { $formulas = @($query.formulas) }
    if ($null -ne $query.PSObject.Properties['dataValidation']) { $dataValidation = @($query.dataValidation) }
    if ($null -ne $query.PSObject.Properties['protection']) { $protection = $query.protection }
    if ($null -ne $query.PSObject.Properties['charts']) { $charts = @($query.charts) }
    if ($null -ne $query.PSObject.Properties['pivots']) { $pivots = @($query.pivots) }
    if ($null -ne $query.PSObject.Properties['slicers']) { $slicers = @($query.slicers) }
    if ($null -ne $query.PSObject.Properties['timelines']) { $timelines = @($query.timelines) }

    return [pscustomobject]@{
        workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
        backend = if ($null -ne $query.PSObject.Properties['backend']) { [string]$query.backend } else { 'excel' }
        sourceFormat = if ($null -ne $query.PSObject.Properties['sourceFormat']) { [string]$query.sourceFormat } else { [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant() }
        workingPath = if ($null -ne $query.PSObject.Properties['workingPath']) { [string]$query.workingPath } else { [System.IO.Path]::GetFullPath($WorkbookPath) }
        normalization = if ($null -ne $query.PSObject.Properties['normalization']) { [string]$query.normalization } else { 'none' }
        warnings = if ($null -ne $query.PSObject.Properties['warnings']) { ConvertTo-ObjectArray -Value $query.warnings } else { @() }
        stagesTried = if ($null -ne $query.PSObject.Properties['stagesTried']) { ConvertTo-ObjectArray -Value $query.stagesTried } else { @() }
        capabilities = if ($null -ne $query.PSObject.Properties['capabilities']) { $query.capabilities } else { $null }
        unsupported = if ($null -ne $query.PSObject.Properties['unsupported']) { ConvertTo-ObjectArray -Value $query.unsupported } else { @() }
        counts = [pscustomobject]@{
            sheets = $sheets.Count
            tables = $tables.Count
            names = $names.Count
            cf = $cf.Count
            pq = $pq.Count
            connections = $connections.Count
            modelTables = if ($null -ne $model -and $null -ne $model.PSObject.Properties['modelTables']) { @($model.modelTables).Count } else { 0 }
            vba = $vba.Count
            references = $references.Count
            formulas = $formulas.Count
            dataValidation = $dataValidation.Count
            protectedSheets = if ($null -ne $protection -and $null -ne $protection.PSObject.Properties['worksheets']) { @($protection.worksheets).Count } else { 0 }
            workbookProtection = if ($null -ne $protection -and $null -ne $protection.PSObject.Properties['workbook'] -and $null -ne $protection.workbook) { 1 } else { 0 }
            charts = $charts.Count
            pivots = $pivots.Count
            slicers = $slicers.Count
            timelines = $timelines.Count
        }
        project = $project
        supportedCfTypes = @($cf | Where-Object { $_.supported } | Select-Object -ExpandProperty type -Unique | Sort-Object)
        unsupportedCfTypes = @($cf | Where-Object { -not $_.supported } | Select-Object -ExpandProperty type -Unique | Sort-Object)
    }
}

function Convert-ExcelSheetTypeName {
    param(
        $Sheet
    )

    $sheetType = $null
    try { $sheetType = [int]$Sheet.Type } catch {}

    switch ($sheetType) {
        -4167 { return 'worksheet' }
        -4109 { return 'chartsheet' }
        -4116 { return 'dialogsheet' }
        3 { return 'macrosheet' }
        default { return 'sheet' }
    }
}

function Convert-ExcelSheetVisibilityName {
    param(
        $Sheet
    )

    $visibleValue = $null
    try { $visibleValue = [int]$Sheet.Visible } catch {}

    switch ($visibleValue) {
        2 { return 'veryHidden' }
        0 { return 'hidden' }
        default { return 'visible' }
    }
}

function Get-ExcelWorkbookLifecycleInspection {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [switch]$Visible,
        [ValidateSet('auto', 'excel', 'package')]
        [string]$Backend = 'auto'
    )

    $packageReadable = Test-OoxmlPackageWorkbook -WorkbookPath $WorkbookPath
    if ($Backend -ne 'excel' -and $packageReadable) {
        return (Invoke-PackageWorkbookHelper -Command 'inspect-lite' -WorkbookPath $WorkbookPath)
    }
    $extension = [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant()
    if ($extension -in @('.csv', '.txt', '.ods')) {
        $capabilityPayload = Invoke-PackageWorkbookHelper -Command 'workbook-capabilities' -WorkbookPath $WorkbookPath
        $metadataWarning = if ($extension -eq '.ods') {
            'OpenDocument lifecycle inspection is metadata-only; use compatibility, convert, or explicit query surfaces when desktop Excel access is required.'
        }
        else {
            'Flat-text lifecycle inspection is metadata-only; use compatibility or convert for worksheet-to-workbook planning.'
        }
        return [pscustomobject]@{
            workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
            backend = 'multi-engine'
            sourceFormat = $extension
            workingPath = [System.IO.Path]::GetFullPath($WorkbookPath)
            normalization = 'none'
            warnings = @($metadataWarning)
            stagesTried = @('metadata')
            capabilities = $capabilityPayload.capabilities
            unsupported = @(
                [pscustomobject]@{
                    surface = 'tables'
                    backend = 'package'
                    reason = if ($extension -eq '.ods') {
                        'OpenDocument lifecycle inspection stays metadata-only by default to avoid slow desktop enumeration; use explicit query surfaces when you need deeper workbook objects.'
                    }
                    else {
                        'Flat-text files do not expose workbook object metadata without opening them in Excel.'
                    }
                }
            )
            counts = [pscustomobject]@{
                workbook = 1
                sheets = 1
                tables = 0
                names = 0
                cf = 0
                pq = 0
                connections = 0
                modelTables = 0
                vba = 0
                references = 0
                formulas = 0
                dataValidation = 0
                charts = 0
                pivots = 0
                hyperlinks = 0
                comments = 0
                dimensionSheets = 1
                printSheets = 1
                protectedSheets = 0
                workbookProtection = 0
            }
            workbook = [pscustomobject]@{
                name = [System.IO.Path]::GetFileName($WorkbookPath)
                path = [System.IO.Path]::GetFullPath($WorkbookPath)
                format = $extension
                packageReadable = $false
                hasVbaProject = $false
                hasExternalLinks = $false
                properties = [pscustomobject]@{
                    core = [pscustomobject]@{}
                    app = [pscustomobject]@{}
                    custom = [pscustomobject]@{}
                }
            }
            sheets = @(
                [pscustomobject]@{
                    name = [System.IO.Path]::GetFileNameWithoutExtension($WorkbookPath)
                    sheetType = 'worksheet'
                    visibility = 'visible'
                }
            )
            project = $null
            supportedCfTypes = @()
            unsupportedCfTypes = @()
        }
    }

    $context = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible -ReadOnlyIntent
    try {
        $sheetPayload = New-Object System.Collections.Generic.List[object]
        $tablesCount = 0
        $namesCount = 0
        $cfCount = 0
        $formulasCount = 0
        $hyperlinksCount = 0
        $commentsCount = 0
        $chartsCount = 0
        $pivotsCount = 0
        $protectedSheetsCount = 0
        $dataValidationCount = 0

        try { $namesCount = [int]$context.Workbook.Names.Count } catch {}

        foreach ($sheet in @($context.Workbook.Sheets)) {
            $sheetType = Convert-ExcelSheetTypeName -Sheet $sheet
            $sheetPayload.Add([pscustomobject]@{
                name = [string]$sheet.Name
                sheetType = $sheetType
                visibility = Convert-ExcelSheetVisibilityName -Sheet $sheet
            }) | Out-Null

            if ($sheetType -eq 'chartsheet') {
                $chartsCount += 1
                continue
            }

            $usedRange = $null
            $formulaCells = $null
            $chartObjects = $null
            $pivotTables = $null
            $comments = $null
            $threadedComments = $null
            try {
                try { $tablesCount += [int]$sheet.ListObjects.Count } catch {}
                try { $hyperlinksCount += [int]$sheet.Hyperlinks.Count } catch {}
                try {
                    $chartObjects = $sheet.ChartObjects()
                    if ($null -ne $chartObjects) {
                        $chartsCount += [int]$chartObjects.Count
                    }
                }
                catch {}
                try {
                    $pivotTables = $sheet.PivotTables()
                    if ($null -ne $pivotTables) {
                        $pivotsCount += [int]$pivotTables.Count
                    }
                }
                catch {}
                try {
                    if ([bool]$sheet.ProtectContents) {
                        $protectedSheetsCount += 1
                    }
                }
                catch {}
                try {
                    $comments = $sheet.Comments
                    if ($null -ne $comments) {
                        $commentsCount += [int]$comments.Count
                    }
                }
                catch {}
                try {
                    $threadedComments = Get-LateProperty -Target $sheet -Name 'CommentsThreaded'
                    if ($null -ne $threadedComments) {
                        $commentsCount += [int]$threadedComments.Count
                    }
                }
                catch {}
                try {
                    $usedRange = $sheet.UsedRange
                    if ($null -ne $usedRange) {
                        try {
                            $formulaCells = $usedRange.SpecialCells(-4123)
                            if ($null -ne $formulaCells) {
                                try { $formulasCount += [int64]$formulaCells.CountLarge } catch { $formulasCount += [int]$formulaCells.Count }
                            }
                        }
                        catch {}
                        try { $cfCount += [int]$usedRange.FormatConditions.Count } catch {}
                    }
                }
                catch {}
                try {
                    $validation = Get-LateProperty -Target $sheet -Name 'Cells'
                    if ($null -ne $validation) {
                        $validationCount = $null
                        try { $validationCount = [int]$validation.Validation.Count } catch {}
                        if ($null -ne $validationCount) {
                            $dataValidationCount += $validationCount
                        }
                    }
                }
                catch {}
            }
            finally {
                Release-ComObjectSafely -Object $formulaCells
                Release-ComObjectSafely -Object $usedRange
                Release-ComObjectSafely -Object $chartObjects
                Release-ComObjectSafely -Object $pivotTables
                Release-ComObjectSafely -Object $comments
                Release-ComObjectSafely -Object $threadedComments
                Release-ComObjectSafely -Object $sheet
            }
        }

        $customProperties = [ordered]@{}
        try {
            foreach ($property in @($context.Workbook.CustomDocumentProperties)) {
                try {
                    $customProperties[[string]$property.Name] = $property.Value
                }
                finally {
                    Release-ComObjectSafely -Object $property
                }
            }
        }
        catch {}

        $powerQueryInfo = Get-WorkbookPowerQueryArtifacts -Workbook $context.Workbook
        $links = @(Get-WorkbookLinkInventory -Workbook $context.Workbook)
        $hasExternalLinks = @($links).Count -gt 0

        return [pscustomobject]@{
            workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
            backend = 'excel'
            sourceFormat = [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant()
            workingPath = [System.IO.Path]::GetFullPath($WorkbookPath)
            normalization = 'none'
            warnings = @()
            stagesTried = @('excel')
            capabilities = (Get-ExcelBackendCapabilities -Context $context)
            unsupported = @()
            counts = [pscustomobject]@{
                workbook = 1
                sheets = $sheetPayload.Count
                tables = $tablesCount
                names = $namesCount
                cf = $cfCount
                pq = @($powerQueryInfo.queries).Count
                connections = @($powerQueryInfo.connections).Count
                modelTables = @($powerQueryInfo.modelTables).Count
                vba = 0
                references = 0
                formulas = $formulasCount
                dataValidation = $dataValidationCount
                charts = $chartsCount
                pivots = $pivotsCount
                hyperlinks = $hyperlinksCount
                comments = $commentsCount
                dimensionSheets = $sheetPayload.Count
                printSheets = $sheetPayload.Count
                protectedSheets = $protectedSheetsCount
                workbookProtection = if ([bool]$context.Workbook.ProtectStructure) { 1 } else { 0 }
            }
            workbook = [pscustomobject]@{
                name = [System.IO.Path]::GetFileName($WorkbookPath)
                path = [System.IO.Path]::GetFullPath($WorkbookPath)
                format = [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant()
                packageReadable = $packageReadable
                hasVbaProject = ([System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant() -in @('.xlsm', '.xlsb', '.xlam', '.xltm', '.xls'))
                hasExternalLinks = $hasExternalLinks
                properties = [pscustomobject]@{
                    core = [pscustomobject]@{}
                    app = [pscustomobject]@{}
                    custom = [pscustomobject]$customProperties
                }
            }
            sheets = @($sheetPayload.ToArray())
            project = $null
            supportedCfTypes = @()
            unsupportedCfTypes = @()
        }
    }
    finally {
        Close-ExcelWorkbook -Context $context -SaveChanges:$false
    }
}

function Invoke-DirectPackageReadFallback {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('table-get', 'query-get', 'connection-list', 'connection-get', 'chart-list', 'chart-get', 'pivot-list', 'pivot-get')]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Table = @(),
        [string[]]$QueryName = @(),
        [string[]]$Connection = @(),
        [string[]]$Chart = @(),
        [string[]]$Pivot = @()
    )

    switch ($Command) {
        'table-get' {
            if (@($Table).Count -lt 1) {
                throw "table get requires --table"
            }
            $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface @('tables')
            $item = Get-DirectWorkbookItemByName -Items @($payload.tables) -Name ([string]$Table[0])
            if ($null -eq $item) {
                throw "Table not found: $($Table[0])"
            }
            return [pscustomobject]@{
                command = $Command
                backend = 'package'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                table = $item
            }
        }
        'query-get' {
            if (@($QueryName).Count -lt 1) {
                throw "query get requires --query-name"
            }
            $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface @('pq')
            $item = Get-DirectWorkbookItemByName -Items @($payload.pq) -Name ([string]$QueryName[0])
            if ($null -eq $item) {
                throw "Power Query not found: $($QueryName[0])"
            }
            return [pscustomobject]@{
                command = $Command
                backend = 'package'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                query = $item
            }
        }
        'connection-list' {
            $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface @('connections')
            return [pscustomobject]@{
                command = $Command
                backend = 'package'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                connections = @($payload.connections)
            }
        }
        'connection-get' {
            if (@($Connection).Count -lt 1) {
                throw "connection get requires --connection"
            }
            $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface @('connections')
            $item = Get-DirectWorkbookItemByName -Items @($payload.connections) -Name ([string]$Connection[0])
            if ($null -eq $item) {
                throw "Connection not found: $($Connection[0])"
            }
            return [pscustomobject]@{
                command = $Command
                backend = 'package'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                connection = $item
            }
        }
        'chart-list' {
            $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface @('charts')
            return [pscustomobject]@{
                command = $Command
                backend = 'package'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                charts = @($payload.charts)
            }
        }
        'chart-get' {
            if (@($Chart).Count -lt 1) {
                throw "chart get requires --chart"
            }
            $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface @('charts')
            $item = Get-DirectWorkbookItemByName -Items @($payload.charts) -Name ([string]$Chart[0])
            if ($null -eq $item) {
                throw "Chart not found: $($Chart[0])"
            }
            return [pscustomobject]@{
                command = $Command
                backend = 'package'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                chart = $item
            }
        }
        'pivot-list' {
            $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface @('pivots')
            return [pscustomobject]@{
                command = $Command
                backend = 'package'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                pivots = @($payload.pivots)
            }
        }
        'pivot-get' {
            if (@($Pivot).Count -lt 1) {
                throw "pivot get requires --pivot"
            }
            $payload = Invoke-PackageWorkbookHelper -Command 'query' -WorkbookPath $WorkbookPath -Surface @('pivots')
            $item = Get-DirectWorkbookItemByName -Items @($payload.pivots) -Name ([string]$Pivot[0])
            if ($null -eq $item) {
                throw "Pivot not found: $($Pivot[0])"
            }
            return [pscustomobject]@{
                command = $Command
                backend = 'package'
                workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
                pivot = $item
            }
        }
    }
}

function Invoke-ExcelWorkbookBootstrap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [Parameter(Mandatory = $true)]
        [string]$OutputDir,
        [string]$ManifestPath,
        [string[]]$Surface = @(),
        [switch]$Visible,
        [ValidateSet('auto', 'excel', 'package')]
        [string]$Backend = 'auto'
    )

    $normalizedSurface = if (@($Surface).Count -gt 0) {
        @($Surface)
    }
    else {
        @('tables', 'names', 'cf', 'pq', 'connections', 'model', 'slicers', 'timelines')
    }

    if ($Backend -eq 'package') {
        return (Invoke-PackageWorkbookHelper -Command 'bootstrap' -WorkbookPath $WorkbookPath -Surface $normalizedSurface -OutputDir $OutputDir -ManifestPath $ManifestPath)
    }

    $queryPayload = Get-ExcelWorkbookQuery -WorkbookPath $WorkbookPath -Surface $normalizedSurface -Visible:$Visible -Backend $Backend
    return (Write-ExcelWorkbookBootstrapArtifacts -WorkbookPath $WorkbookPath -OutputDir $OutputDir -ManifestPath $ManifestPath -QueryPayload $queryPayload)
}

function Invoke-ExcelFoundrySmoke {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ManifestPath,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Surface = @(),
        [switch]$Visible
    )

    $manifestDirectory = Split-Path -Parent ([System.IO.Path]::GetFullPath($ManifestPath))
    $tempRoot = Join-Path $env:TEMP ("excel_foundry_smoke_{0}_{1}" -f $PID, [System.Guid]::NewGuid().ToString('N'))
    $tempWorkspace = Join-Path $tempRoot 'workspace'
    $tempManifestPath = Join-Path $tempWorkspace (Split-Path -Leaf $ManifestPath)
    $relativeWorkbookPath = Resolve-RelativePath -BasePath $manifestDirectory -TargetPath $WorkbookPath
    $useWorkspaceWorkbook = -not [string]::IsNullOrWhiteSpace($relativeWorkbookPath) -and -not $relativeWorkbookPath.StartsWith('..')
    $tempWorkbookPath = if ($useWorkspaceWorkbook) {
        Join-Path $tempWorkspace $relativeWorkbookPath
    }
    else {
        Join-Path $tempWorkspace (Split-Path -Leaf $WorkbookPath)
    }

    try {
        Copy-Item -LiteralPath $manifestDirectory -Destination $tempWorkspace -Recurse -Force
        if (-not $useWorkspaceWorkbook) {
            Copy-Item -LiteralPath $WorkbookPath -Destination $tempWorkbookPath -Force
        }

        Write-Output ("SMOKE SETUP workspace={0}" -f $tempWorkspace)
        Write-Output "SMOKE ROUNDTRIP"
        & (Join-Path $PSScriptRoot 'sync-foundry.ps1') -ManifestPath $tempManifestPath -Direction 'roundtrip' -WorkbookPath $tempWorkbookPath -Visible:$Visible
        Write-Output "SMOKE INSPECT"
        $inspection = Get-ExcelWorkbookInspection -WorkbookPath $tempWorkbookPath -Surface $Surface -Visible:$Visible
        Write-Output ("SMOKE OK tables={0} names={1} cf={2} vba={3}" -f $inspection.counts.tables, $inspection.counts.names, $inspection.counts.cf, $inspection.counts.vba)
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

