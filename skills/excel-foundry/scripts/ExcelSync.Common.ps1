Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

    return (Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json -Depth 100)
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

function Resolve-ExcelSyncManifest {
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
    $script:ExcelSyncLastOpenDiagnostics = $null

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

            $script:ExcelSyncLastOpenDiagnostics = [pscustomobject]@{
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
        OpenDiagnostics = $script:ExcelSyncLastOpenDiagnostics
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
    $state = $Context.State

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
        [Parameter(Mandatory = $true)]
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

function Remove-VbaComponentIfImportable {
    param(
        [Parameter(Mandatory = $true)]
        $Workbook,
        [Parameter(Mandatory = $true)]
        [string]$ComponentName
    )

    $component = Resolve-VbaComponent -Workbook $Workbook -ComponentName $ComponentName
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

    $component = Resolve-VbaComponent -Workbook $Workbook -ComponentName $ComponentName
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

        $component = Resolve-VbaComponent -Workbook $Workbook -ComponentName $ComponentName
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
        [ValidateSet('query', 'inspect', 'inspect-lite', 'bootstrap', 'mutate-audit', 'plan', 'compare', 'sync', 'workbook-capabilities', 'workbook-inspect', 'workbook-create', 'workbook-diff', 'manifest-validate', 'manifest-doctor', 'manifest-migrate', 'sheet-list', 'sheet-create', 'name-list', 'name-set', 'name-delete', 'table-list', 'table-read', 'query-list', 'cell-get', 'cell-set', 'range-get', 'range-set')]
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
        [string]$ValueJson,
        [string]$ValuesJson,
        [string]$SpecJson,
        [string]$SpecFile,
        [string]$RefersTo,
        [switch]$Hidden,
        [string]$StateRoot,
        [switch]$Apply,
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
        foreach ($argument in @($launcherArgs + $arguments)) {
            [void]$startInfo.ArgumentList.Add([string]$argument)
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
                $parsedPayload = $stdout | ConvertFrom-Json -Depth 100
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
        return ($stdout | ConvertFrom-Json -Depth 100)
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

    Write-JsonFile -Path $sheetsPath -Value ([pscustomobject]@{ sheets = if ($null -ne $QueryPayload.PSObject.Properties['sheets']) { @($QueryPayload.sheets) } else { @() } })
    Write-JsonFile -Path $tablesPath -Value ([pscustomobject]@{ tables = @($QueryPayload.tables) })
    Write-JsonFile -Path $namesPath -Value ([pscustomobject]@{ names = @($QueryPayload.names) })
    Write-JsonFile -Path $cfPath -Value ([pscustomobject]@{ rules = @($QueryPayload.cf) })
    Write-JsonFile -Path $formulasPath -Value ([pscustomobject]@{ formulas = if ($null -ne $QueryPayload.PSObject.Properties['formulas']) { @($QueryPayload.formulas) } else { @() } })
    Write-JsonFile -Path $dataValidationPath -Value ([pscustomobject]@{ rules = if ($null -ne $QueryPayload.PSObject.Properties['dataValidation']) { @($QueryPayload.dataValidation) } else { @() } })
    Write-JsonFile -Path $protectionPath -Value ($(if ($null -ne $QueryPayload.PSObject.Properties['protection']) { $QueryPayload.protection } else { [pscustomobject]@{ workbook = $null; worksheets = @() } }))
    Write-JsonFile -Path $chartsPath -Value ([pscustomobject]@{ charts = if ($null -ne $QueryPayload.PSObject.Properties['charts']) { @($QueryPayload.charts) } else { @() } })
    Write-JsonFile -Path $pivotsPath -Value ([pscustomobject]@{ pivots = if ($null -ne $QueryPayload.PSObject.Properties['pivots']) { @($QueryPayload.pivots) } else { @() } })

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
    if ($null -ne $QueryPayload.PSObject.Properties['pq']) { $pq = @($QueryPayload.pq) }
    if ($null -ne $QueryPayload.PSObject.Properties['connections']) { $connections = @($QueryPayload.connections) }
    if ($null -ne $QueryPayload.PSObject.Properties['model'] -and $null -ne $QueryPayload.model.PSObject.Properties['modelTables']) {
        $modelTables = @($QueryPayload.model.modelTables)
    }

    if ($pq.Count -gt 0 -or $connections.Count -gt 0 -or $modelTables.Count -gt 0) {
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
        Write-JsonFile -Path (Join-Path $powerQueryDirectory 'model.json') -Value ([pscustomobject]@{ modelTables = $modelTables })
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

function Get-WorkbookModelArtifacts {
    param($Workbook)

    try {
        $modelTables = $Workbook.Model.ModelTables
    }
    catch {
        return @()
    }

    $tables = @()
    foreach ($modelTable in $modelTables) {
        $entry = [ordered]@{
            name = $null
            sourceName = $null
            recordCount = $null
        }
        try { $entry.name = [string]$modelTable.Name } catch {}
        try { $entry.sourceName = [string]$modelTable.SourceName } catch {}
        try { $entry.recordCount = [int]$modelTable.RecordCount } catch {}
        $tables += [pscustomobject]$entry
    }

    return @($tables | Sort-Object name)
}

function Get-WorkbookPowerQueryArtifacts {
    param($Workbook)

    $connections = @(Get-WorkbookConnectionArtifacts -Workbook $Workbook)
    $loads = @(Get-WorkbookQueryLoadArtifacts -Workbook $Workbook)
    $modelTables = @(Get-WorkbookModelArtifacts -Workbook $Workbook)
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
    }
}

function Get-PowerQueryRefreshArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Connections,
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

    if ($null -ne $QueryPayload.PSObject.Properties['pq']) {
        $queries = @($QueryPayload.pq)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['connections']) {
        $connections = @($QueryPayload.connections)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['model'] -and $null -ne $QueryPayload.model.PSObject.Properties['modelTables']) {
        $modelTables = @($QueryPayload.model.modelTables)
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
        Write-JsonFile -Path $powerQuery.ModelPath -Value ([pscustomobject]@{ modelTables = @($modelTables) })
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
        if ($null -ne $modelRoot.PSObject.Properties['modelTables']) {
            $modelTables = @($modelRoot.modelTables)
        }
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
        if (-not [string]::IsNullOrWhiteSpace($powerQuery.QueriesDirectory) -and -not [string]::IsNullOrWhiteSpace([string]$entry.file)) {
            $queryPath = Join-Path $powerQuery.QueriesDirectory ([string]$entry.file)
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
        return ($SpecJson | ConvertFrom-Json -Depth 100)
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
    $topLeft = [string]$TableSpec.topLeft
    if ([string]::IsNullOrWhiteSpace($topLeft)) {
        throw "Table spec requires topLeft."
    }

    $worksheet = Get-WorksheetByName -Workbook $Workbook -WorksheetName $sheetName
    $headerValues = [object[]]@($TableSpec.headers | ForEach-Object { [string]$_ })
    if ($headerValues.Count -lt 1) {
        throw "Table spec requires at least one header."
    }
    $rows = @($TableSpec.rows)
    if ($rows.Count -lt 1) {
        $rows = ,(@("") * $headerValues.Count)
    }

    $allRows = New-Object System.Collections.Generic.List[object[]]
    $allRows.Add($headerValues)
    foreach ($row in $rows) {
        $allRows.Add([object[]]@($row | ForEach-Object { $_ }))
    }

    $existing = Find-ListObjectByName -Worksheet $worksheet -TableName $tableName
    if ($Mode -eq 'create' -and $null -ne $existing) {
        throw "Table already exists: $tableName"
    }
    if ($Mode -eq 'update' -and $null -eq $existing) {
        throw "Table not found: $tableName"
    }

    if ($null -eq $existing) {
        $start = Get-RangeFromAddress -Worksheet $worksheet -Address $topLeft
        $targetRange = Set-RangeValues -Range $start -Values $allRows
        $listObject = $worksheet.ListObjects.Add(1, $targetRange, $null, 1)
        $listObject.Name = $tableName
        return
    }

    $start = $worksheet.Range($topLeft)
    $targetRange = $start.Resize($allRows.Count, $headerValues.Count)
    $existing.Resize($targetRange)
    for ($col = 1; $col -le $headerValues.Count; $col++) {
        $existing.ListColumns.Item($col).Name = [string]$headerValues[$col - 1]
    }

    $bodyRows = @($allRows | Select-Object -Skip 1)
    if ($bodyRows.Count -gt 0) {
        [void](Set-RangeValues -Range $start.Offset(1, 0) -Values $bodyRows)
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
        $workbook = Invoke-ExcelComWithRetry -Description 'Opening workbook in recovery mode' -MaxAttempts 10 -DelayMilliseconds 500 -Operation {
            $excel.Workbooks.Open($WorkbookPath, 0, $true, $null, $null, $null, $true, $null, $null, $false, $false, $null, $false, $true, $CorruptLoad)
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

    $target = Resolve-WorkbookTargetPath `
        -SourcePath $WorkbookPath `
        -TargetPath $TargetPath `
        -TargetFormat $TargetFormat `
        -Suffix '.share-safe'

    Ensure-ParentDirectory -Path $target.path
    $sourceContext = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible
    try {
        $sourceContext.Workbook.SaveCopyAs($target.path)
    }
    finally {
        Close-ExcelWorkbook -Context $sourceContext -SaveChanges:$false
    }

    $copyContext = Open-ExcelWorkbook -WorkbookPath $target.path -Visible:$Visible
    try {
        $inspection = Get-ExcelWorkbookLifecycleInspection `
            -WorkbookPath $target.path `
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

        if ($target.format.extension -ne [System.IO.Path]::GetExtension($target.path).ToLowerInvariant()) {
            $target.path = [System.IO.Path]::ChangeExtension($target.path, $target.format.extension)
        }
        $copyContext.Workbook.SaveAs($target.path, $target.format.fileFormat)

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
    }
}

function Invoke-DirectExcelWorkbookCommand {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('workbook-save-as', 'workbook-convert', 'workbook-repair', 'workbook-compatibility', 'workbook-document-inspect', 'workbook-links', 'workbook-break-links', 'workbook-repoint-links', 'workbook-safe-export', 'table-get', 'table-create', 'table-update', 'table-delete', 'query-get', 'query-set', 'query-delete', 'query-refresh', 'connection-list', 'connection-get', 'chart-list', 'chart-get', 'pivot-list', 'pivot-get')]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Table = @(),
        [string[]]$QueryName = @(),
        [string[]]$Connection = @(),
        [string[]]$Chart = @(),
        [string[]]$Pivot = @(),
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
                openDiagnostics = $script:ExcelSyncLastOpenDiagnostics
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

    $readOnlyDirectCommands = @('workbook-links', 'table-get', 'query-get', 'connection-list', 'connection-get', 'chart-list', 'chart-get', 'pivot-list', 'pivot-get')
    $packageFallbackCommands = @('table-get', 'query-get', 'connection-list', 'connection-get', 'chart-list', 'chart-get', 'pivot-list', 'pivot-get')
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
                -Pivot $Pivot
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
                $context.Workbook.SaveCopyAs($target.path)
                $copyContext = Open-ExcelWorkbook -WorkbookPath $target.path -Visible:$Visible
                try {
                    $copyContext.Workbook.SaveAs($target.path, $target.format.fileFormat)
                }
                finally {
                    Close-ExcelWorkbook -Context $copyContext -SaveChanges:$false
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
        if ($null -ne $QuerySpec.description) {
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

    if ($null -ne $QuerySpec.description) {
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
        if ($null -ne $ConnectionSpec.oledb) {
            $oledb = $Connection.OLEDBConnection
            if ($null -ne $oledb) {
                foreach ($item in @(
                    @{ Name = 'BackgroundQuery'; Value = $ConnectionSpec.oledb.backgroundQuery },
                    @{ Name = 'RefreshOnFileOpen'; Value = $ConnectionSpec.oledb.refreshOnFileOpen },
                    @{ Name = 'RefreshWithRefreshAll'; Value = $ConnectionSpec.oledb.refreshWithRefreshAll }
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

    $excelOnlySurfaces = @('vba', 'project', 'references')
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
        @('tables', 'names', 'cf', 'pq', 'connections', 'model')
    }

    if ($Backend -eq 'package') {
        return (Invoke-PackageWorkbookHelper -Command 'bootstrap' -WorkbookPath $WorkbookPath -Surface $normalizedSurface -OutputDir $OutputDir -ManifestPath $ManifestPath)
    }

    $queryPayload = Get-ExcelWorkbookQuery -WorkbookPath $WorkbookPath -Surface $normalizedSurface -Visible:$Visible -Backend $Backend
    return (Write-ExcelWorkbookBootstrapArtifacts -WorkbookPath $WorkbookPath -OutputDir $OutputDir -ManifestPath $ManifestPath -QueryPayload $queryPayload)
}

function Invoke-ExcelSyncSmoke {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ManifestPath,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Surface = @(),
        [switch]$Visible
    )

    $manifestDirectory = Split-Path -Parent ([System.IO.Path]::GetFullPath($ManifestPath))
    $tempRoot = Join-Path $env:TEMP ("excel_sync_smoke_{0}_{1}" -f $PID, [System.Guid]::NewGuid().ToString('N'))
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
        & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $tempManifestPath -Direction 'roundtrip' -WorkbookPath $tempWorkbookPath -Visible:$Visible
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

