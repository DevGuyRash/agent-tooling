param(
    [Parameter(ValueFromPipeline = $true)]
    [string]$InputObject,
    [string]$EventsFile = '',
    [string]$IndexFile = '',
    [string]$RepoRoot = '',
    [string]$Path = '',
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:PayloadLines = [System.Collections.Generic.List[string]]::new()

function Show-Help {
@"
Usage:
  .\scripts\report-friction-json.ps1 [-EventsFile PATH] [-RepoRoot PATH] [-Path FILE]
  ... | .\scripts\report-friction-json.ps1 [-EventsFile PATH] [-RepoRoot PATH]

Thin helper for the safe JSON filing path. Forwards to report-friction.ps1
using -FromJson so callers do not need to hand-quote complex payload text.
"@
}

process {
    if ($null -ne $InputObject) {
        $script:PayloadLines.Add([string]$InputObject)
    }
}

end {
    if ($Help) {
        Show-Help
        return
    }

    $reportArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($EventsFile)) { $reportArgs += @('-EventsFile', $EventsFile) }
    if (-not [string]::IsNullOrWhiteSpace($IndexFile)) { $reportArgs += @('-IndexFile', $IndexFile) }
    if (-not [string]::IsNullOrWhiteSpace($RepoRoot)) { $reportArgs += @('-RepoRoot', $RepoRoot) }

    if (-not [string]::IsNullOrWhiteSpace($Path)) {
        & "$PSScriptRoot/report-friction.ps1" @reportArgs -FromJson $Path
        return
    }

    if ($script:PayloadLines.Count -eq 0 -and [Console]::IsInputRedirected -eq $false) {
        Show-Help
        return
    }

    ($script:PayloadLines -join [Environment]::NewLine) | & "$PSScriptRoot/report-friction.ps1" @reportArgs -FromJson '-'
}
