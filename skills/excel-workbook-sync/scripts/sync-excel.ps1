param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [ValidateSet("push", "pull", "roundtrip", "refresh")]
    [string]$Direction = "push",
    [string]$WorkbookPath,
    [string[]]$QueryName = @(),
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'ExcelSync.Common.ps1')

$vbaScript = Join-Path $PSScriptRoot "sync-excel-vba.ps1"
$structureScript = Join-Path $PSScriptRoot "sync-excel-structure.ps1"
$powerQueryScript = Join-Path $PSScriptRoot "sync-excel-powerquery.ps1"

function Invoke-SyncStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [Parameter(Mandatory = $true)]
        [string]$ManifestPath,
        [Parameter(Mandatory = $true)]
        [string]$Direction,
        [string]$WorkbookPath,
        [string[]]$QueryName = @(),
        [switch]$Visible
    )

    $params = @{
        ManifestPath = $ManifestPath
        Direction = $Direction
    }
    if (-not [string]::IsNullOrWhiteSpace($WorkbookPath)) {
        $params.WorkbookPath = $WorkbookPath
    }
    if (@($QueryName).Count -gt 0) {
        $params.QueryName = @($QueryName)
    }
    if ($Visible) {
        $params.Visible = $true
    }

    & $ScriptPath @params
}

function Invoke-SyncStepWithFallbackContext {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [Parameter(Mandatory = $true)]
        [string]$ManifestPath,
        [Parameter(Mandatory = $true)]
        [string]$Direction,
        [string]$WorkbookPath,
        [string[]]$QueryName = @(),
        [switch]$Visible
    )

    try {
        Invoke-SyncStep -ScriptPath $ScriptPath -ManifestPath $ManifestPath -Direction $Direction -WorkbookPath $WorkbookPath -QueryName $QueryName -Visible:$Visible
    }
    catch {
        $resolvedWorkbookPath = $WorkbookPath
        if ([string]::IsNullOrWhiteSpace($resolvedWorkbookPath) -and -not [string]::IsNullOrWhiteSpace($ManifestPath)) {
            try {
                $resolved = Resolve-ExcelSyncManifest -ManifestPath $ManifestPath -WorkbookPathOverride $WorkbookPath
                $resolvedWorkbookPath = $resolved.WorkbookPath
            }
            catch {
            }
        }

        if ($Direction -in @('push', 'roundtrip', 'refresh') -and
            -not [string]::IsNullOrWhiteSpace($resolvedWorkbookPath) -and
            (Test-OoxmlPackageWorkbook -WorkbookPath $resolvedWorkbookPath)) {
            throw "Package fallback is currently read-only for $Direction. This workbook is package-readable, but Excel COM could not complete the write-capable operation. Use inspect/query/bootstrap/pull, or open the workbook successfully in desktop Excel before retrying $Direction."
        }

        throw
    }
}

switch ($Direction) {
    "push" {
        Invoke-SyncStepWithFallbackContext -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
    }
    "pull" {
        Invoke-SyncStepWithFallbackContext -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
    }
    "roundtrip" {
        Invoke-SyncStepWithFallbackContext -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStepWithFallbackContext -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
    }
    "refresh" {
        Invoke-SyncStepWithFallbackContext -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "refresh" -WorkbookPath $WorkbookPath -QueryName $QueryName -Visible:$Visible
    }
}
