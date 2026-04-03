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

    return [pscustomobject]@{
        ManifestPath = $manifestFullPath
        ManifestDirectory = $manifestDir
        WorkbookPath = $resolvedWorkbookPath
        VbaComponents = $resolvedVbaComponents
        VbaProject = $resolvedVbaProject
        Structure = $resolvedStructure
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
        $workbook = Invoke-LateMethod -Target $excel.Workbooks -Name 'Open' -Arguments @(
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
        try {
            $workbook = $excel.Workbooks.Open($WorkbookPath)
        }
        catch {
            try {
                $excel.Quit()
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
            throw
        }
    }

    if ($null -eq $workbook) {
        try {
            $excel.Quit()
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
            Invoke-ExcelComWithRetry -Description "Quitting Excel" -Operation {
                $excel.Quit()
            } | Out-Null
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
        [switch]$Visible
    )

    $context = Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible
    try {
        $payload = [ordered]@{
            workbookPath = $WorkbookPath
        }

        if (Test-SurfaceRequested -Surface $Surface -Name 'tables') {
            $payload["tables"] = @(Get-TableQuery -Workbook $context.Workbook)
        }
        if (Test-SurfaceRequested -Surface $Surface -Name 'names') {
            $payload["names"] = @(Get-NameQuery -Workbook $context.Workbook)
        }
        if (Test-SurfaceRequested -Surface $Surface -Name 'cf') {
            $payload["cf"] = @(Get-ConditionalFormattingQuery -Workbook $context.Workbook)
        }
        if ((Test-SurfaceRequested -Surface $Surface -Name 'vba') -or
            (Test-SurfaceRequested -Surface $Surface -Name 'project') -or
            (Test-SurfaceRequested -Surface $Surface -Name 'references')) {
            $projectInfo = Get-VbaProjectInfo -Workbook $context.Workbook
            if (Test-SurfaceRequested -Surface $Surface -Name 'vba') {
                $payload["vba"] = @($projectInfo.components)
            }
            if (Test-SurfaceRequested -Surface $Surface -Name 'project') {
                $payload["project"] = [pscustomobject]@{
                    accessible = $projectInfo.accessible
                    error = $projectInfo.error
                    componentCount = @($projectInfo.components).Count
                    referenceCount = @($projectInfo.references).Count
                }
            }
            if (Test-SurfaceRequested -Surface $Surface -Name 'references') {
                $payload["references"] = @($projectInfo.references)
            }
        }

        return [pscustomobject]$payload
    }
    finally {
        Close-ExcelWorkbook -Context $context -SaveChanges:$false
    }
}

function Get-ExcelWorkbookInspection {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkbookPath,
        [string[]]$Surface = @(),
        [switch]$Visible
    )

    $query = Get-ExcelWorkbookQuery -WorkbookPath $WorkbookPath -Surface $Surface -Visible:$Visible
    $tables = @()
    $names = @()
    $cf = @()
    $vba = @()
    $references = @()
    $project = $null

    if ($null -ne $query.PSObject.Properties['tables']) { $tables = @($query.tables) }
    if ($null -ne $query.PSObject.Properties['names']) { $names = @($query.names) }
    if ($null -ne $query.PSObject.Properties['cf']) { $cf = @($query.cf) }
    if ($null -ne $query.PSObject.Properties['vba']) { $vba = @($query.vba) }
    if ($null -ne $query.PSObject.Properties['references']) { $references = @($query.references) }
    if ($null -ne $query.PSObject.Properties['project']) { $project = $query.project }

    return [pscustomobject]@{
        workbookPath = $WorkbookPath
        counts = [pscustomobject]@{
            tables = $tables.Count
            names = $names.Count
            cf = $cf.Count
            vba = $vba.Count
            references = $references.Count
        }
        project = $project
        supportedCfTypes = @($cf | Where-Object { $_.supported } | Select-Object -ExpandProperty type -Unique | Sort-Object)
        unsupportedCfTypes = @($cf | Where-Object { -not $_.supported } | Select-Object -ExpandProperty type -Unique | Sort-Object)
    }
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

    $tempPath = Join-Path $env:TEMP ("excel_sync_smoke_{0}{1}" -f $PID, [System.IO.Path]::GetExtension($WorkbookPath))
    try {
        Copy-Item -LiteralPath $WorkbookPath -Destination $tempPath -Force
        & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $ManifestPath -Direction 'roundtrip' -WorkbookPath $tempPath -Visible:$Visible | Out-Null
        $inspection = Get-ExcelWorkbookInspection -WorkbookPath $tempPath -Surface $Surface -Visible:$Visible
        Write-Output ("SMOKE OK tables={0} names={1} cf={2} vba={3}" -f $inspection.counts.tables, $inspection.counts.names, $inspection.counts.cf, $inspection.counts.vba)
    }
    finally {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
    }
}
