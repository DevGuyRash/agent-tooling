param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [ValidateSet("push", "pull", "roundtrip")]
    [string]$Direction = "push",
    [string]$WorkbookPath,
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$vbaScript = Join-Path $PSScriptRoot "sync-excel-vba.ps1"
$structureScript = Join-Path $PSScriptRoot "sync-excel-structure.ps1"

function Invoke-SyncStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [Parameter(Mandatory = $true)]
        [string]$ManifestPath,
        [Parameter(Mandatory = $true)]
        [string]$Direction,
        [string]$WorkbookPath,
        [switch]$Visible
    )

    $params = @{
        ManifestPath = $ManifestPath
        Direction = $Direction
    }
    if (-not [string]::IsNullOrWhiteSpace($WorkbookPath)) {
        $params.WorkbookPath = $WorkbookPath
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
    }
    "pull" {
        Invoke-SyncStep -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
    }
    "roundtrip" {
        Invoke-SyncStep -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "push" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $structureScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
        Invoke-SyncStep -ScriptPath $vbaScript -ManifestPath $ManifestPath -Direction "pull" -WorkbookPath $WorkbookPath -Visible:$Visible
    }
}
