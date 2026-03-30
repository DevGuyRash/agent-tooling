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

# Helper: get tags from an event
function Get-EventTags {
    param($event)
    $tags = $event.tags
    if ($null -ne $tags -and $tags -is [System.Array]) {
        return @($tags | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { [string]$_ })
    }
    return @()
}

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
    $tagCounts = @{}

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

        foreach ($tag in (Get-EventTags $event)) {
            if (-not $tagCounts.ContainsKey($tag)) {
                $tagCounts[$tag] = 0
            }
            $tagCounts[$tag]++
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

    if ($tagCounts.Count -gt 0) {
        $lines += ''
        $lines += '## Tags'
        $lines += ''
        $sortedTagCounts = $tagCounts.GetEnumerator() | Sort-Object -Property @(
            @{ Expression = { $_.Value }; Descending = $true }
            @{ Expression = { $_.Name }; Descending = $false }
        )
        foreach ($item in $sortedTagCounts) {
            $lines += "- ``$($item.Key)`` - $($item.Value)"
        }
    }
    else {
        $lines += ''
        $lines += '## Tags'
        $lines += ''
        $lines += '_No tags recorded._'
    }

    $lines += ''
    $lines += '## Recent events'
    $lines += ''
    foreach ($event in $recentEvents) {
        $title = [string]$event.title
        $provenanceSource = [string]$event.provenance_source
        $sourcesDisplay = ''
        $sources = $event.sources
        if ($null -ne $sources -and $sources -is [System.Array] -and $sources.Count -gt 0) {
            $refs = @($sources | Where-Object { $null -ne $_ } | ForEach-Object { [string]$_.ref } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
            if ($refs.Count -gt 0) {
                $sourcesDisplay = " [$($refs -join ', ')]"
            }
        }
        if ($provenanceSource -eq 'explicit') {
            $agent = Get-AgentDisplay -Agent ([string]$event.agent_name) -Role ([string]$event.role)
            $lines += "- ``$($event.recorded_at)`` ``$($event.derived_category)`` ``$agent``$sourcesDisplay - $title"
        }
        else {
            $lines += "- ``$($event.recorded_at)`` ``$($event.derived_category)``$sourcesDisplay - $title"
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
