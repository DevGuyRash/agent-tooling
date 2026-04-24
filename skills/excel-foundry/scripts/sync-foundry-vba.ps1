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

$resolved = Resolve-ExcelFoundryManifest -ManifestPath $ManifestPath -WorkbookPathOverride $WorkbookPath
if ($resolved.VbaComponents.Count -eq 0 -and
    -not $resolved.VbaProject.ProjectPath -and
    -not $resolved.VbaProject.ReferencesPath) {
    Write-Output ("SKIP VBA no VBA artifacts configured in manifest: {0}" -f $ManifestPath)
    return
}

$context = Open-ExcelWorkbook -WorkbookPath $resolved.WorkbookPath -Visible:$Visible

try {
    $projectInfo = Get-VbaProjectInfo -Workbook $context.Workbook
    $vbComponents = $null
    try { $vbComponents = $context.Workbook.VBProject.VBComponents } catch {}
    $moduleMutationSupported = $false
    if ($null -ne $vbComponents) {
        $moduleMutationSupported = (@($vbComponents | Get-Member -Name Import).Count -gt 0) -or (@($vbComponents | Get-Member -Name Add).Count -gt 0)
    }

    if (-not $projectInfo.accessible) {
        Write-Output ("SKIP VBA project access is unavailable for: {0}" -f $resolved.WorkbookPath)
        return
    }
    if ($Direction -eq "push" -and -not $moduleMutationSupported) {
        Write-Output ("SKIP VBA module mutation is unavailable for: {0}" -f $resolved.WorkbookPath)
        return
    }

    foreach ($component in $resolved.VbaComponents) {
        if ($Direction -eq "push") {
            Set-VbaComponentArtifact -Workbook $context.Workbook -ComponentName $component.Name -SourcePath $component.Path
            Write-Output ("PUSH VBA {0} <= {1}" -f $component.Name, $component.Path)
        }
        else {
            try {
                $writtenPath = Export-VbaComponentArtifact -Workbook $context.Workbook -ComponentName $component.Name -DestinationPath $component.Path
                Write-Output ("PULL VBA {0} => {1}" -f $component.Name, $writtenPath)
            }
            catch {
                if ($_.Exception.Message -like 'Workbook VBA component not found:*') {
                    Write-Output ("SKIP VBA missing component {0} in workbook: {1}" -f $component.Name, $resolved.WorkbookPath)
                    continue
                }
                throw
            }
        }
    }

    if ($resolved.VbaProject.ProjectPath) {
        if ($Direction -eq "push") {
            $projectArtifact = Read-JsonFile -Path $resolved.VbaProject.ProjectPath
            if ($null -ne $projectArtifact.components) {
                Write-Output ("PUSH VBA PROJECT <= {0}" -f $resolved.VbaProject.ProjectPath)
            }
        }
        else {
            $projectArtifact = Get-VbaProjectArtifact -Workbook $context.Workbook
            Write-JsonFile -Path $resolved.VbaProject.ProjectPath -Value $projectArtifact
            Write-Output ("PULL VBA PROJECT => {0}" -f $resolved.VbaProject.ProjectPath)
        }
    }

    if ($resolved.VbaProject.ReferencesPath) {
        if ($Direction -eq "push") {
            $referenceArtifact = Read-JsonFile -Path $resolved.VbaProject.ReferencesPath
            Ensure-VbaReferences -Workbook $context.Workbook -ReferenceArtifact $referenceArtifact
            Write-Output ("PUSH VBA REFERENCES <= {0}" -f $resolved.VbaProject.ReferencesPath)
        }
        else {
            $referenceArtifact = Get-VbaReferenceArtifacts -Workbook $context.Workbook
            Write-JsonFile -Path $resolved.VbaProject.ReferencesPath -Value $referenceArtifact
            Write-Output ("PULL VBA REFERENCES => {0}" -f $resolved.VbaProject.ReferencesPath)
        }
    }

    $context.Workbook.Save()
}
finally {
    Close-ExcelWorkbook -Context $context -SaveChanges:$true
}
