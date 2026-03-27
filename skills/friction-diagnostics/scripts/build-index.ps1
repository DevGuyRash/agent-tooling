param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$IndexFile = $env:FRICTION_INDEX_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/build-index.ps1
  scripts/build-index.ps1 -RepoRoot <repo>
  scripts/build-index.ps1 -EventsFile /path/to/events.jsonl [-IndexFile /path/to/INDEX.md]
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

$paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile -IndexFile $IndexFile
$EventsFile = $paths.EventsFile
$IndexFile = $paths.IndexFile
$RepoRoot = $paths.RepoRoot

$indexTempFile = $null
Invoke-WithFileLock -LockRoot $IndexFile -ScriptBlock {
    $events = Import-Events $EventsFile

    if ($events.Count -eq 0) {
        Remove-Item -Force -ErrorAction SilentlyContinue $IndexFile
        return
    }

    $generated = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss') + ' UTC'
    $categoryCounts = @{}
    $agentCounts = @{}
    $openIncidentIds = [System.Collections.Generic.HashSet[string]]::new()
    $allIncidentIds = [System.Collections.Generic.HashSet[string]]::new()

    foreach ($event in $events) {
        if (-not [string]::IsNullOrWhiteSpace($event.derived_category)) {
            if (-not $categoryCounts.ContainsKey($event.derived_category)) {
                $categoryCounts[$event.derived_category] = 0
            }
            $categoryCounts[$event.derived_category]++
        }

        $provenanceSource = [string]$event.provenance_source
        if ($provenanceSource -eq 'explicit' -and -not [string]::IsNullOrWhiteSpace([string]$event.agent_kind)) {
            if (-not $agentCounts.ContainsKey([string]$event.agent_kind)) {
                $agentCounts[[string]$event.agent_kind] = 0
            }
            $agentCounts[[string]$event.agent_kind]++
        }

        if (-not [string]::IsNullOrWhiteSpace($event.incident_id)) {
            $null = $allIncidentIds.Add([string]$event.incident_id)
            if ([string]$event.incident_status -ne 'mitigated') {
                $null = $openIncidentIds.Add([string]$event.incident_id)
            }
        }
    }

    $recentEvents = $events |
        Sort-Object -Property @{ Expression = { $_.recorded_at }; Descending = $true }, @{ Expression = { $_.event_id }; Descending = $true } |
        Select-Object -First 10

    $lines = @(
        '# Friction Index'
    )
    $lines += Write-MarkdownField -Label 'Generated' -Value $generated
    if (-not [string]::IsNullOrWhiteSpace($RepoRoot)) {
        $lines += Write-MarkdownField -Label 'Repo root' -Value $RepoRoot
    }
    $lines += Write-MarkdownField -Label 'Events file' -Value $EventsFile
    $lines += Write-MarkdownField -Label 'Entries' -Value ([string]$events.Count)
    $lines += Write-MarkdownField -Label 'Incidents' -Value ([string]$allIncidentIds.Count)
    $lines += Write-MarkdownField -Label 'Open incidents' -Value ([string]$openIncidentIds.Count)
    $lines += ''
    $lines += '## Category counts'
    $lines += ''

    $sortedCategoryCounts = $categoryCounts.GetEnumerator() | Sort-Object -Property @(
        @{ Expression = { $_.Value }; Descending = $true }
        @{ Expression = { $_.Name }; Descending = $false }
    )
    foreach ($item in $sortedCategoryCounts) {
        $lines += "- ``$($item.Key)`` - $($item.Value)"
    }

    if ($agentCounts.Count -gt 0) {
        $lines += ''
        $lines += '## Agent counts'
        $lines += ''
        $sortedAgentCounts = $agentCounts.GetEnumerator() | Sort-Object -Property @(
            @{ Expression = { $_.Value }; Descending = $true }
            @{ Expression = { $_.Name }; Descending = $false }
        )
        foreach ($item in $sortedAgentCounts) {
            $lines += "- ``$($item.Name)`` - $($item.Value)"
        }
    }
    else {
        $lines += ''
        $lines += '## Agent counts'
        $lines += ''
        $lines += '_No explicit provenance recorded._'
    }

    $lines += ''
    $lines += '## Recent events'
    $lines += ''
    foreach ($event in $recentEvents) {
        $title = if (-not [string]::IsNullOrWhiteSpace($event.title_line)) { $event.title_line } else { $event.title }
        $provenanceSource = [string]$event.provenance_source
        if ($provenanceSource -eq 'explicit') {
            $agent = Get-AgentDisplay -Agent ([string]$event.agent_name) -Role ([string]$event.role)
            $lines += "- ``$($event.recorded_at)`` ``$($event.derived_category)`` ``$agent`` - $title"
        }
        else {
            $lines += "- ``$($event.recorded_at)`` ``$($event.derived_category)`` - $title"
        }
    }

    $indexTempFile = Join-Path (Split-Path -Parent $IndexFile) (".index.{0}.tmp" -f [System.IO.Path]::GetRandomFileName())
    Set-Content -Path $indexTempFile -Value $lines -Encoding UTF8
    Move-Item -Force -Path $indexTempFile -Destination $IndexFile
    $indexTempFile = $null
}

if ($null -ne $indexTempFile -and (Test-Path -LiteralPath $indexTempFile)) {
    Remove-Item -Force -ErrorAction SilentlyContinue $indexTempFile
}

if (Test-Path -LiteralPath $IndexFile) {
    $IndexFile
}
