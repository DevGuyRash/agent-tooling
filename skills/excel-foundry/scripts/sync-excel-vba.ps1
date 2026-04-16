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

. (Join-Path $PSScriptRoot "ExcelSync.Common.ps1")

$resolved = Resolve-ExcelSyncManifest -ManifestPath $ManifestPath -WorkbookPathOverride $WorkbookPath
if ($resolved.VbaComponents.Count -eq 0 -and
    -not $resolved.VbaProject.ProjectPath -and
    -not $resolved.VbaProject.ReferencesPath) {
    Write-Output ("SKIP VBA no VBA artifacts configured in manifest: {0}" -f $ManifestPath)
    return
}

$context = Open-ExcelWorkbook -WorkbookPath $resolved.WorkbookPath -Visible:$Visible

try {
    foreach ($component in $resolved.VbaComponents) {
        if ($Direction -eq "push") {
            Set-VbaComponentArtifact -Workbook $context.Workbook -ComponentName $component.Name -SourcePath $component.Path
            Write-Output ("PUSH VBA {0} <= {1}" -f $component.Name, $component.Path)
        }
        else {
            $writtenPath = Export-VbaComponentArtifact -Workbook $context.Workbook -ComponentName $component.Name -DestinationPath $component.Path
            Write-Output ("PULL VBA {0} => {1}" -f $component.Name, $writtenPath)
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
