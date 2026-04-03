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

switch ($Direction) {
    "push" {
        Invoke-SyncStep -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
    }
    "pull" {
        Invoke-SyncStep -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
    }
    "roundtrip" {
        Invoke-SyncStep -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
    }
    "refresh" {
        Invoke-SyncStep -ScriptPath $powerQueryScript -ManifestPath $ManifestPath -Direction "refresh" -WorkbookPath $WorkbookPath -QueryName $QueryName -Visible:$Visible
    }
}
