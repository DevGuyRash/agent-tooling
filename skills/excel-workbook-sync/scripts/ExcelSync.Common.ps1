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

    $resolvedVbaComponents = @()
    foreach ($component in @($manifest.vbaComponents)) {
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

    $structure = $manifest.structure
    $resolvedStructure = [pscustomobject]@{
        TablesPath = $null
        NamesPath = $null
        ConditionalFormattingPath = $null
        TablesDiscovery = $null
        NamesDiscovery = $null
        ConditionalFormattingDiscovery = $null
    }

    if ($null -ne $structure) {
        if ($null -ne $structure.PSObject.Properties['tablesPath'] -and $null -ne $structure.tablesPath) {
            $resolvedStructure.TablesPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.tablesPath)
        }
        if ($null -ne $structure.PSObject.Properties['namesPath'] -and $null -ne $structure.namesPath) {
            $resolvedStructure.NamesPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.namesPath)
        }
        if ($null -ne $structure.PSObject.Properties['conditionalFormattingPath'] -and $null -ne $structure.conditionalFormattingPath) {
            $resolvedStructure.ConditionalFormattingPath = Resolve-AbsolutePath -BasePath $manifestDir -RelativeOrAbsolutePath ([string]$structure.conditionalFormattingPath)
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
        [switch]$Visible
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
    [void](Try-SetProperty -Target $excel -Name 'AutomationSecurity' -Value 3)

    try {
        $workbook = Invoke-ExcelComWithRetry -Description "Opening workbook" -MaxAttempts 20 -DelayMilliseconds 500 -Operation {
            try {
                return Invoke-LateMethod -Target $excel.Workbooks -Name 'Open' -Arguments @(
                    $WorkbookPath,
                    0,
                    $false,
                    $null,
                    $null,
                    $null,
                    $true,
                    $null,
                    $null,
                    $false,
                    $false
                )
            }
            catch {
                return $excel.Workbooks.Open($WorkbookPath)
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
    }
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

    $vbProject = Get-LateProperty -Target $Workbook -Name "VBProject"
    $vbComponents = Get-LateProperty -Target $vbProject -Name "VBComponents"
    Invoke-LateMethod -Target $vbComponents -Name "Remove" -Arguments @($component) | Out-Null
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
            $vbProject = Get-LateProperty -Target $Workbook -Name "VBProject"
            $vbComponents = Get-LateProperty -Target $vbProject -Name "VBComponents"
            $imported = Get-LateProperty -Target $vbComponents -Name "Import" -Arguments @($SourcePath)
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
        [string]$Surface
    )

    $aliases = @{
        'conditional-formatting' = 'cf'
        'conditional_formatting' = 'cf'
        'power-query' = 'pq'
        'power_query' = 'pq'
    }

    return @(
        $Surface -split ',' |
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
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue | Out-Null
        $archive = [System.IO.Compression.ZipFile]::OpenRead($WorkbookPath)
        $archive.Dispose()
        return $true
    }
    catch {
        return $false
    }
}

function Invoke-PackageWorkbookHelper {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('query', 'inspect', 'bootstrap')]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Surface = @(),
        [string]$OutputDir,
        [string]$ManifestPath
    )

    $pythonCommand = @(Get-PythonLauncher)
    $scriptPath = Join-Path $PSScriptRoot 'excel_workbook_package.py'
    $arguments = @($scriptPath, $Command, '--workbook-path', $WorkbookPath)
    if (@($Surface).Count -gt 0) {
        $arguments += @('--surface', (@($Surface) -join ','))
    }
    if ($Command -eq 'bootstrap') {
        if ([string]::IsNullOrWhiteSpace($OutputDir)) {
            throw "OutputDir is required for bootstrap."
        }
        $arguments += @('--output-dir', $OutputDir)
        if (-not [string]::IsNullOrWhiteSpace($ManifestPath)) {
            $arguments += @('--manifest-path', $ManifestPath)
        }
    }

    $launcherArgs = @()
    if ($pythonCommand.Count -gt 1) {
        $launcherArgs = @($pythonCommand[1..($pythonCommand.Count - 1)])
    }

    $json = & $pythonCommand[0] @launcherArgs @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Package workbook helper failed for $Command."
    }

    return ($json | ConvertFrom-Json -Depth 100)
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
    $tablesPath = Join-Path $structureRoot 'tables.json'
    $namesPath = Join-Path $structureRoot 'names.json'
    $cfPath = Join-Path $structureRoot 'conditional_formatting.json'

    Write-JsonFile -Path $tablesPath -Value ([pscustomobject]@{ tables = @($QueryPayload.tables) })
    Write-JsonFile -Path $namesPath -Value ([pscustomobject]@{ names = @($QueryPayload.names) })
    Write-JsonFile -Path $cfPath -Value ([pscustomobject]@{ rules = @($QueryPayload.cf) })

    $manifest = [ordered]@{
        workbookPath = Get-ManifestRelativeWorkbookPath -ManifestDirectory $manifestDirectory -WorkbookPath $WorkbookPath
        vbaComponents = @()
        structure = [ordered]@{
            tablesPath = 'workbook_structure/tables.json'
            namesPath = 'workbook_structure/names.json'
            conditionalFormattingPath = 'workbook_structure/conditional_formatting.json'
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

    $tables = @()
    $names = @()
    $rules = @()

    if ($null -ne $QueryPayload.PSObject.Properties['tables']) {
        $tables = @($QueryPayload.tables)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['names']) {
        $names = @($QueryPayload.names)
    }
    if ($null -ne $QueryPayload.PSObject.Properties['cf']) {
        $rules = @($QueryPayload.cf)
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
    param($Excel)

    try {
        Invoke-LateMethod -Target $Excel -Name 'CalculateUntilAsyncQueriesDone' | Out-Null
    }
    catch {
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
            Wait-ForExcelAsyncQueries -Excel $Workbook.Application
        }
        catch {
            $errorText = $_.Exception.Message
        }

        $results += [pscustomobject]@{
            name = [string]$target.name
            success = [string]::IsNullOrWhiteSpace($errorText)
            error = $errorText
            elapsedSeconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 3)
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

function Get-ExcelWorkbookQuery {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Surface = @(),
        [switch]$Visible,
        [ValidateSet('auto', 'excel', 'package')]
        [string]$Backend = 'auto'
    )

    $normalizedSurface = @($Surface | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    $warnings = New-Object System.Collections.Generic.List[string]
    $stagesTried = New-Object System.Collections.Generic.List[string]

    if ($Backend -in @('auto', 'excel')) {
        $stagesTried.Add('excel')
        try {
            $context = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible
            try {
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

                return [pscustomobject]$payload
            }
            finally {
                Close-ExcelWorkbook -Context $context -SaveChanges:$false
            }
        }
        catch {
            if ($Backend -eq 'excel' -or -not (Test-OoxmlPackageWorkbook -WorkbookPath $WorkbookPath)) {
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
    $vba = @()
    $references = @()
    $project = $null

    if ($null -ne $query.PSObject.Properties['tables']) { $tables = @($query.tables) }
    if ($null -ne $query.PSObject.Properties['names']) { $names = @($query.names) }
    if ($null -ne $query.PSObject.Properties['cf']) { $cf = @($query.cf) }
    if ($null -ne $query.PSObject.Properties['pq']) { $pq = @($query.pq) }
    if ($null -ne $query.PSObject.Properties['connections']) { $connections = @($query.connections) }
    if ($null -ne $query.PSObject.Properties['model']) { $model = $query.model }
    if ($null -ne $query.PSObject.Properties['vba']) { $vba = @($query.vba) }
    if ($null -ne $query.PSObject.Properties['references']) { $references = @($query.references) }
    if ($null -ne $query.PSObject.Properties['project']) { $project = $query.project }

    return [pscustomobject]@{
        workbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
        backend = if ($null -ne $query.PSObject.Properties['backend']) { [string]$query.backend } else { 'excel' }
        sourceFormat = if ($null -ne $query.PSObject.Properties['sourceFormat']) { [string]$query.sourceFormat } else { [System.IO.Path]::GetExtension($WorkbookPath).ToLowerInvariant() }
        workingPath = if ($null -ne $query.PSObject.Properties['workingPath']) { [string]$query.workingPath } else { [System.IO.Path]::GetFullPath($WorkbookPath) }
        normalization = if ($null -ne $query.PSObject.Properties['normalization']) { [string]$query.normalization } else { 'none' }
        warnings = if ($null -ne $query.PSObject.Properties['warnings']) { ConvertTo-ObjectArray -Value $query.warnings } else { @() }
        stagesTried = if ($null -ne $query.PSObject.Properties['stagesTried']) { ConvertTo-ObjectArray -Value $query.stagesTried } else { @() }
        counts = [pscustomobject]@{
            tables = $tables.Count
            names = $names.Count
            cf = $cf.Count
            pq = $pq.Count
            connections = $connections.Count
            modelTables = if ($null -ne $model -and $null -ne $model.PSObject.Properties['modelTables']) { @($model.modelTables).Count } else { 0 }
            vba = $vba.Count
            references = $references.Count
        }
        project = $project
        supportedCfTypes = @($cf | Where-Object { $_.supported } | Select-Object -ExpandProperty type -Unique | Sort-Object)
        unsupportedCfTypes = @($cf | Where-Object { -not $_.supported } | Select-Object -ExpandProperty type -Unique | Sort-Object)
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
