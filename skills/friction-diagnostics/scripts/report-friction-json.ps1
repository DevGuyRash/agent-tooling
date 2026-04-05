param(
    [string]$EventsFile = '',
    [string]$RepoRoot = '',
    [string]$Path = '',
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Show-Help {
@"
Usage:
  .\scripts\report-friction-json.ps1 [-EventsFile PATH] [-RepoRoot PATH] [-Path FILE]
  ... | .\scripts\report-friction-json.ps1 [-EventsFile PATH] [-RepoRoot PATH]

Thin helper for the safe JSON filing path. Forwards to report-friction.ps1
using -FromJson so callers do not need to hand-quote complex payload text.
"@
}

if ($Help) {
    Show-Help
    return
}

$reportScript = Join-Path $PSScriptRoot 'report-friction.ps1'

function Write-HelperOutput {
    param([object[]]$ReportOutput)

    foreach ($line in @($ReportOutput)) {
        $text = [string]$line
        switch -Regex ($text) {
            '^events_file=(.+)$' { Write-Output "FRICTION_EVENTS_FILE=$($Matches[1])"; continue }
            '^index_file=(.+)$' { Write-Output "FRICTION_INDEX_FILE=$($Matches[1])"; continue }
            '^event_id=(.+)$' { Write-Output "FRICTION_EVENT_ID=$($Matches[1])"; continue }
            '^repo_root=(.+)$' { Write-Output "FRICTION_REPO_ROOT=$($Matches[1])"; continue }
            default { Write-Output $text }
        }
    }
}

function Invoke-ReportScript {
    param([string]$FromJsonPath)

    $args = @('-FromJson', $FromJsonPath)
    if (-not [string]::IsNullOrWhiteSpace($EventsFile)) {
        $args = @('-EventsFile', $EventsFile) + $args
    }
    if (-not [string]::IsNullOrWhiteSpace($RepoRoot)) {
        $args = @('-RepoRoot', $RepoRoot) + $args
    }
    return & $reportScript @args
}

if (-not [string]::IsNullOrWhiteSpace($Path)) {
    $reportOutput = Invoke-ReportScript -FromJsonPath $Path
    Write-HelperOutput $reportOutput
    return
}

$payloadLines = @($input | ForEach-Object { [string]$_ })
if ($payloadLines.Count -eq 0 -and [Console]::IsInputRedirected -eq $false) {
    Show-Help
    return
}

$stdinText = if ($payloadLines.Count -gt 0) {
    $payloadLines -join [Environment]::NewLine
} else {
    [Console]::In.ReadToEnd()
}

if ([string]::IsNullOrWhiteSpace($stdinText)) {
    Show-Help
    return
}

$tempPath = Join-Path ([System.IO.Path]::GetTempPath()) ("report-friction-json.{0}.json" -f [System.Guid]::NewGuid().ToString('N'))
try {
    [System.IO.File]::WriteAllText($tempPath, $stdinText, [System.Text.UTF8Encoding]::new($false))
    $reportOutput = Invoke-ReportScript -FromJsonPath $tempPath
    Write-HelperOutput $reportOutput
}
finally {
    if (Test-Path -LiteralPath $tempPath) {
        Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
    }
}
