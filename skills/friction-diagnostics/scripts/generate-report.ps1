param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string[]]$ScanDirs = @(),
    [string]$Impact = '',
    [string]$Fingerprint = '',
    [string]$Tag = '',
    [string]$TagExact = '',
    [string]$Alias = '',
    [string]$AliasExact = '',
    [string]$Text = '',
    [string]$Date = '',
    [string]$DateFrom = '',
    [string]$DateTo = '',
    [string]$After = '',
    [string]$SourceRef = '',
    [ValidateSet('index', 'cross-repo', 'per-repo', 'timeseries')][string]$ReportType = 'index',
    [ValidateSet('', 'impact', 'alias', 'tag')][string]$GroupBy = '',
    [ValidateSet('md', 'json')][string]$Format = 'md',
    [string]$Output = '',
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/generate-report.ps1 [-EventsFile PATH | -ScanDirs DIR [DIR...]] [filters] [report options]

Input:
  -EventsFile PATH         Single events file (default: auto-detected)
  -ScanDirs DIR [DIR...]   Recursively discover all events.jsonl files under
                           the given directories matching
                           */.local*/reports/friction/events.jsonl

Filters:
  -Impact VALUE
  -Fingerprint VALUE
  -Tag VALUE               Substring match across tags
  -TagExact VALUE          Exact tag match
  -Alias VALUE             Substring match across aliases
  -AliasExact VALUE        Exact alias match
  -Text PATTERN            Case-insensitive substring search across narrative fields
  -Date YYYY-MM-DD
  -DateFrom YYYY-MM-DD
  -DateTo YYYY-MM-DD
  -After ISO-TIMESTAMP     Filter events with recorded_at > TIMESTAMP
  -SourceRef PATH

Report:
  -ReportType index|cross-repo|per-repo|timeseries
  -GroupBy impact|alias|tag
  -Format md|json
  -Output PATH
  -Help
"@
    exit 0
}

if (-not [string]::IsNullOrWhiteSpace($GroupBy) -and $ReportType -ne 'timeseries') {
    throw '-GroupBy is only supported with -ReportType timeseries'
}

. "$PSScriptRoot/_Common.ps1"

function Get-EventTags {
    param($event)
    $tags = Get-EventFieldValue -event $event -Name 'tags'
    if ($null -eq $tags) { return @() }
    return @(@($tags) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ })
}

function Get-EventAliases {
    param($event)
    $aliases = Get-EventFieldValue -event $event -Name 'aliases'
    if ($null -eq $aliases) { return @() }
    return @(@($aliases) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ })
}

function Get-EventSourceRefs {
    param($event)
    $sources = Get-EventFieldValue -event $event -Name 'sources'
    if ($null -eq $sources) { return @() }
    return @(@($sources) | Where-Object { $null -ne $_ -and -not [string]::IsNullOrWhiteSpace([string]$_.ref) } | ForEach-Object { [string]$_.ref })
}

function Test-SourceRefMatch {
    param($event, [string]$ref)
    return (Get-EventSourceRefs $event) -contains $ref
}

function Get-RepoRootFromEventsFile {
    param([string]$Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if ($fullPath -match '^(.*?)[/\\]\.local[^/\\]*[/\\]reports[/\\]friction[/\\]events\.jsonl$') {
        return $matches[1]
    }
    return ''
}

function Get-RelativeEventsFile {
    param(
        [string]$RepoRoot,
        [string]$Path
    )
    if ([string]::IsNullOrWhiteSpace($RepoRoot)) { return $Path }
    try {
        $repoUri = [System.Uri](([System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\', '/')) + [System.IO.Path]::DirectorySeparatorChar)
        $pathUri = [System.Uri][System.IO.Path]::GetFullPath($Path)
        $relativeUri = $repoUri.MakeRelativeUri($pathUri)
        return [System.Uri]::UnescapeDataString($relativeUri.ToString()).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    }
    catch {
        return $Path
    }
}

function Get-ValueOrFallback {
    param(
        $Value,
        $Fallback
    )
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) {
        return $Fallback
    }
    return $Value
}

function Add-CounterValue {
    param(
        [hashtable]$Counter,
        [string]$Key,
        [int]$Amount = 1
    )
    if ([string]::IsNullOrWhiteSpace($Key)) { return }
    if (-not $Counter.ContainsKey($Key)) {
        $Counter[$Key] = 0
    }
    $Counter[$Key] += $Amount
}

function Get-PercentString {
    param(
        [int]$Count,
        [int]$Total
    )
    if ($Total -le 0) { return '0%' }
    return ('{0:0}%' -f (($Count * 100.0) / $Total))
}

function Convert-CounterToRows {
    param(
        [hashtable]$Counter,
        [int]$Total = 0,
        [switch]$WithPercent,
        [int]$Limit = 0,
        [switch]$SortByValue
    )
    $items = if ($SortByValue) {
        $Counter.GetEnumerator() | Sort-Object -Property Name
    }
    else {
        $Counter.GetEnumerator() | Sort-Object -Property @(
            @{ Expression = { $_.Value }; Descending = $true }
            @{ Expression = { $_.Name }; Descending = $false }
        )
    }
    if ($Limit -gt 0) {
        $items = $items | Select-Object -First $Limit
    }
    $rows = foreach ($item in $items) {
        if ($WithPercent) {
            [pscustomobject]@{
                value = [string]$item.Key
                count = [int]$item.Value
                percent = Get-PercentString -Count ([int]$item.Value) -Total $Total
            }
        }
        else {
            [pscustomobject]@{
                value = [string]$item.Key
                count = [int]$item.Value
            }
        }
    }
    return @($rows)
}

function Get-ImpactCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        Add-CounterValue -Counter $counter -Key ([string](Get-EventFieldValue -event $event -Name 'impact' -Default ''))
    }
    return $counter
}

function Get-FingerprintCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        Add-CounterValue -Counter $counter -Key ([string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default ''))
    }
    return $counter
}

function Get-DateCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        $ts = [string](Get-EventFieldValue -event $event -Name 'recorded_at' -Default '')
        if (-not [string]::IsNullOrWhiteSpace($ts) -and $ts.Length -ge 10) {
            Add-CounterValue -Counter $counter -Key $ts.Substring(0, 10)
        }
    }
    return $counter
}

function Get-TagCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        $seen = [System.Collections.Generic.HashSet[string]]::new()
        foreach ($tagValue in (Get-EventTags $event)) {
            if ($seen.Add($tagValue)) {
                Add-CounterValue -Counter $counter -Key $tagValue
            }
        }
    }
    return $counter
}

function Get-AliasCounts {
    param([object[]]$Events)
    # Returns rows with value, count (unique events), blocked (unique events with impact=blocked)
    $aliasBuckets = @{}
    for ($i = 0; $i -lt $Events.Count; $i++) {
        $event = $Events[$i]
        $isBlocked = [string](Get-EventFieldValue -event $event -Name 'impact' -Default '') -eq 'blocked'
        foreach ($a in (Get-EventAliases $event)) {
            if ([string]::IsNullOrWhiteSpace($a)) { continue }
            if (-not $aliasBuckets.ContainsKey($a)) {
                $aliasBuckets[$a] = @{ eventIdxs = [System.Collections.Generic.HashSet[int]]::new(); blockedIdxs = [System.Collections.Generic.HashSet[int]]::new() }
            }
            $null = $aliasBuckets[$a].eventIdxs.Add($i)
            if ($isBlocked) { $null = $aliasBuckets[$a].blockedIdxs.Add($i) }
        }
    }
    $rows = @(foreach ($a in $aliasBuckets.Keys) {
        [pscustomobject]@{
            value   = $a
            count   = $aliasBuckets[$a].eventIdxs.Count
            blocked = $aliasBuckets[$a].blockedIdxs.Count
        }
    } | Sort-Object -Property @(
        @{ Expression = { $_.count }; Descending = $true }
        @{ Expression = { $_.value }; Descending = $false }
    ))
    return $rows
}

function Get-SourceCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        foreach ($ref in (Get-EventSourceRefs $event)) {
            Add-CounterValue -Counter $counter -Key $ref
        }
    }
    return $counter
}

function Test-EventMatchesFilters {
    param($event)
    $ts = [string](Get-EventFieldValue -event $event -Name 'recorded_at' -Default '')

    if (-not [string]::IsNullOrWhiteSpace($Impact) -and [string](Get-EventFieldValue -event $event -Name 'impact' -Default '') -ne $Impact) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($Fingerprint) -and [string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default '') -ne $Fingerprint) { return $false }

    # Tag substring filter
    if (-not [string]::IsNullOrWhiteSpace($Tag)) {
        $needle = $Tag.ToLowerInvariant()
        $matched = $false
        foreach ($t in (Get-EventTags $event)) {
            if ($t.ToLowerInvariant().Contains($needle)) { $matched = $true; break }
        }
        if (-not $matched) { return $false }
    }
    # Tag exact filter
    if (-not [string]::IsNullOrWhiteSpace($TagExact)) {
        $needle = $TagExact.ToLowerInvariant()
        $matched = $false
        foreach ($t in (Get-EventTags $event)) {
            if ($t.ToLowerInvariant() -eq $needle) { $matched = $true; break }
        }
        if (-not $matched) { return $false }
    }
    # Alias substring filter
    if (-not [string]::IsNullOrWhiteSpace($Alias)) {
        $needle = $Alias.ToLowerInvariant()
        $matched = $false
        foreach ($a in (Get-EventAliases $event)) {
            if ($a.ToLowerInvariant().Contains($needle)) { $matched = $true; break }
        }
        if (-not $matched) { return $false }
    }
    # Alias exact filter
    if (-not [string]::IsNullOrWhiteSpace($AliasExact)) {
        $needle = $AliasExact.ToLowerInvariant()
        $matched = $false
        foreach ($a in (Get-EventAliases $event)) {
            if ($a.ToLowerInvariant() -eq $needle) { $matched = $true; break }
        }
        if (-not $matched) { return $false }
    }

    if (-not (Test-EventTextMatch -Event $event -Query $Text)) { return $false }
    if (-not (Test-EventTimestampFilters -RecordedAt $ts -Date $Date -DateFrom $DateFrom -DateTo $DateTo -After $After)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($SourceRef) -and -not (Test-SourceRefMatch $event $SourceRef)) { return $false }
    return $true
}

function Get-RepoSummary {
    param(
        [string]$EventsFilePath,
        [object[]]$Events
    )
    $sortedEvents = @($Events | Sort-Object -Property @{ Expression = { [string](Get-EventFieldValue -event $_ -Name 'recorded_at' -Default '') }; Descending = $false }, @{ Expression = { [string](Get-EventFieldValue -event $_ -Name 'event_id' -Default '') }; Descending = $false })
    $repoRootValue = ''
    foreach ($event in $sortedEvents) {
        $repoRootValue = [string](Get-EventFieldValue -event $event -Name '_repo_root' -Default '')
        if (-not [string]::IsNullOrWhiteSpace($repoRootValue)) { break }
        $repoRootValue = [string](Get-EventFieldValue -event $event -Name 'repo_root' -Default '')
        if (-not [string]::IsNullOrWhiteSpace($repoRootValue)) { break }
    }
    if ([string]::IsNullOrWhiteSpace($repoRootValue)) {
        $repoRootValue = Get-RepoRootFromEventsFile $EventsFilePath
    }
    $entries = $sortedEvents.Count
    $blockedCount = @($sortedEvents | Where-Object { [string](Get-EventFieldValue -event $_ -Name 'impact' -Default '') -eq 'blocked' }).Count
    $earliest = if ($entries -gt 0) { [string](Get-EventFieldValue -event $sortedEvents[0] -Name 'recorded_at' -Default '') } else { '' }
    $latest = if ($entries -gt 0) { [string](Get-EventFieldValue -event $sortedEvents[-1] -Name 'recorded_at' -Default '') } else { '' }
    [pscustomobject]@{
        repo_root             = $repoRootValue
        events_file           = $EventsFilePath
        events_file_display   = Get-RelativeEventsFile -RepoRoot $repoRootValue -Path $EventsFilePath
        entries               = $entries
        blocked               = $blockedCount
        earliest_event        = $earliest
        latest_event          = $latest
        events_list           = @($sortedEvents | ForEach-Object {
            [pscustomobject]@{
                event_id   = [string](Get-EventFieldValue -event $_ -Name 'event_id' -Default '')
                recorded_at = [string](Get-EventFieldValue -event $_ -Name 'recorded_at' -Default '')
                title      = [string](Get-EventFieldValue -event $_ -Name 'title' -Default '')
                impact     = [string](Get-EventFieldValue -event $_ -Name 'impact' -Default '')
                aliases    = @(Get-EventAliases $_)
                tags       = @(Get-EventTags $_)
                sources    = @(@(Get-EventFieldValue -event $_ -Name 'sources') | Where-Object { $null -ne $_ } | ForEach-Object {
                    [pscustomobject]@{ ref = [string]$_.ref; line = $_.line; end_line = $_.end_line }
                })
            }
        })
        recurring_patterns    = @(Convert-CounterToRows -Counter (Get-FingerprintCounts $sortedEvents) | Where-Object { $_.count -gt 1 } | Select-Object -First 10)
        alias_counts          = @(Get-AliasCounts $sortedEvents)
        source_counts         = @(Convert-CounterToRows -Counter (Get-SourceCounts $sortedEvents) -Limit 10)
        tag_counts            = @(Convert-CounterToRows -Counter (Get-TagCounts $sortedEvents))
        date_counts           = @(Convert-CounterToRows -Counter (Get-DateCounts $sortedEvents) -SortByValue)
        impact_summary        = @(Convert-CounterToRows -Counter (Get-ImpactCounts $sortedEvents))
        fingerprint_counts    = @(Convert-CounterToRows -Counter (Get-FingerprintCounts $sortedEvents) -Limit 10)
    }
}

function Format-MarkdownTable {
    param(
        [string[]]$Headers,
        [string[][]]$Rows,
        [string]$EmptyMessage
    )
    if ($Rows.Count -eq 0) { return $EmptyMessage }
    $lines = @()
    $lines += '| ' + ($Headers -join ' | ') + ' |'
    $lines += '| ' + (($Headers | ForEach-Object { '---' }) -join ' | ') + ' |'
    foreach ($row in $Rows) {
        $lines += '| ' + ($row -join ' | ') + ' |'
    }
    return ($lines -join "`n")
}

function Render-MarkdownReport {
    param($Report)
    $lines = [System.Collections.Generic.List[string]]::new()
    switch ([string]$Report.report_type) {
        'index' {
            # Compute span in days
            $spanStr = ''
            $earliest = [string](Get-ValueOrFallback $Report.earliest_event '')
            $latest = [string](Get-ValueOrFallback $Report.latest_event '')
            if (-not [string]::IsNullOrWhiteSpace($earliest) -and -not [string]::IsNullOrWhiteSpace($latest) -and $earliest.Length -ge 10 -and $latest.Length -ge 10) {
                try {
                    $ea = [int[]]($earliest.Substring(0,10).Split('-') | ForEach-Object { [int]$_ })
                    $la = [int[]]($latest.Substring(0,10).Split('-') | ForEach-Object { [int]$_ })
                    $spanDays = ($la[0] - $ea[0]) * 365 + ($la[1] - $ea[1]) * 30 + ($la[2] - $ea[2])
                    $spanStr = " | **Span:** $spanDays days"
                } catch { }
            }
            $lines.Add('# Friction Index')
            $lines.Add('')
            $lines.Add("**Created:** $([string](Get-ValueOrFallback $Report.earliest_event '(not available)'))")
            $lines.Add("**Last event:** $([string](Get-ValueOrFallback $Report.latest_event '(not available)'))")
            $lines.Add("**Index rebuilt:** $([string]$Report.index_rebuilt)")
            $lines.Add("**Events:** $([int]$Report.entries) | **Blocked:** $([int]$Report.blocked)$spanStr")
            $lines.Add('')
            $lines.Add('## Events')
            $lines.Add('')
            $eventRows = @(@($Report.events_list) | ForEach-Object {
                $aliasStr = ($_.aliases -join ', ')
                $titleDisplay = if ([string]$_.title.Length -gt 50) { ([string]$_.title).Substring(0, 47) + '...' } else { [string]$_.title }
                [string[]]@([string]$_.event_id, ([string]$_.recorded_at).Substring([Math]::Min(5, ([string]$_.recorded_at).Length), [Math]::Max(0, [Math]::Min(11, ([string]$_.recorded_at).Length - 5))), $titleDisplay, [string]$_.impact, $aliasStr)
            })
            $lines.Add((Format-MarkdownTable -Headers @('ID', 'Time', 'Title', 'Impact', 'Aliases') -Rows $eventRows -EmptyMessage '_No events._'))
            $lines.Add('')
            $lines.Add('## Recurring Patterns')
            $lines.Add('')
            $recurringRows = @(@($Report.recurring_patterns) | ForEach-Object {
                $latestTitle = ''
                $latestImpact = ''
                foreach ($ev in @($Report.events_list)) {
                    if ([string]$ev.impact -ne '' -and $null -ne $ev) {
                        # find matching fingerprint in events_list not available here; omit extended fields
                    }
                }
                [string[]]@([string]$_.value, [string]$_.count)
            })
            $lines.Add((Format-MarkdownTable -Headers @('Fingerprint', 'Count') -Rows $recurringRows -EmptyMessage '_No recurring patterns._'))
            $lines.Add('')
            $lines.Add('## By Alias')
            $lines.Add('')
            $aliasRows = @(@($Report.alias_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.blocked) })
            $lines.Add((Format-MarkdownTable -Headers @('Alias', 'Events', 'Blocked') -Rows $aliasRows -EmptyMessage '_No aliases recorded._'))
            $lines.Add('')
            $lines.Add('## By Source')
            $lines.Add('')
            $sourceRows = @(@($Report.source_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Source', 'Events') -Rows $sourceRows -EmptyMessage '_No sources recorded._'))
            $lines.Add('')
            $lines.Add('## Tags')
            $lines.Add('')
            $tagRows = @(@($Report.tag_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Tag', 'Events') -Rows $tagRows -EmptyMessage '_No tags recorded._'))
            $lines.Add('')
            $lines.Add('## Date Distribution')
            $lines.Add('')
            $dateRows = @(@($Report.date_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Date', 'Count') -Rows $dateRows -EmptyMessage '_No date counts available._'))
        }
        'cross-repo' {
            $lines.Add('# Cross-Repo Friction Index')
            $lines.Add('')
            $lines.Add("**Index rebuilt:** $([string]$Report.index_rebuilt)")
            $lines.Add("**Repos scanned:** $([int]$Report.repos_scanned)")
            $lines.Add("**Total entries:** $([int]$Report.total_entries)")
            $lines.Add('')
            $lines.Add('## Repos')
            $lines.Add('')
            if (@($Report.repos).Count -eq 0) {
                $lines.Add('_No repos matched._')
            }
            else {
                foreach ($repo in @($Report.repos)) {
                    $label = if (-not [string]::IsNullOrWhiteSpace([string]$repo.repo_root)) { [string]$repo.repo_root } else { [string]$repo.events_file }
                    $lines.Add("- ``$label`` — $([int]$repo.entries) events")
                }
            }
            $lines.Add('')
            $lines.Add('## Impact Summary')
            $lines.Add('')
            $impactRows = @(@($Report.impact_summary) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Impact', 'Count') -Rows $impactRows -EmptyMessage '_No events._'))
            $lines.Add('')
            $lines.Add('## Aliases')
            $lines.Add('')
            $aliasRows = @(@($Report.alias_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.percent) })
            $lines.Add((Format-MarkdownTable -Headers @('Alias', 'Count', '%') -Rows $aliasRows -EmptyMessage '_No aliases recorded._'))
            $lines.Add('')
            $lines.Add('## Tags')
            $lines.Add('')
            $tagRows = @(@($Report.tag_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.percent) })
            $lines.Add((Format-MarkdownTable -Headers @('Tag', 'Count', '%') -Rows $tagRows -EmptyMessage '_No tags recorded._'))
            $lines.Add('')
            $lines.Add('## Top Fingerprints')
            $lines.Add('')
            $fpRows = @(@($Report.fingerprint_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Fingerprint', 'Count') -Rows $fpRows -EmptyMessage '_No fingerprints._'))
        }
        'per-repo' {
            $lines.Add('# Per-Repo Friction Report')
            $lines.Add('')
            $lines.Add("**Index rebuilt:** $([string]$Report.index_rebuilt)")
            $lines.Add("**Repos:** $([int]$Report.repos) | **Total entries:** $([int]$Report.total_entries)")
            if (@($Report.repo_summaries).Count -eq 0) {
                $lines.Add('')
                $lines.Add('_No repos matched the selected filters._')
            }
            else {
                foreach ($repo in @($Report.repo_summaries)) {
                    $label = if (-not [string]::IsNullOrWhiteSpace([string]$repo.repo_root)) { [string]$repo.repo_root } else { [string]$repo.events_file }
                    $lines.Add('')
                    $lines.Add('---')
                    $lines.Add('')
                    $lines.Add("## $label")
                    $lines.Add("**Entries:** $([int]$repo.entries) | **Earliest:** $([string](Get-ValueOrFallback $repo.earliest_event '')[0..9] -join '') | **Latest:** $([string](Get-ValueOrFallback $repo.latest_event '')[0..9] -join '')")
                    $lines.Add('')
                    $lines.Add('### Impact')
                    $lines.Add('')
                    $repoImpactRows = @(@($repo.impact_summary) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
                    $lines.Add((Format-MarkdownTable -Headers @('Impact', 'Count') -Rows $repoImpactRows -EmptyMessage '_No events._'))
                    $lines.Add('')
                    $lines.Add('### Aliases')
                    $lines.Add('')
                    $repoAliasRows = @(@($repo.alias_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.blocked) })
                    $lines.Add((Format-MarkdownTable -Headers @('Alias', 'Count', 'Blocked') -Rows $repoAliasRows -EmptyMessage '_No aliases._'))
                    $lines.Add('')
                    $lines.Add('### Tags')
                    $lines.Add('')
                    $repoTagRows = @(@($repo.tag_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
                    $lines.Add((Format-MarkdownTable -Headers @('Tag', 'Count') -Rows $repoTagRows -EmptyMessage '_No tags._'))
                }
            }
        }
        'timeseries' {
            $title = '# Friction Time Series'
            if (-not [string]::IsNullOrWhiteSpace([string]$Report.group_by)) {
                $title = "# Friction Time Series (by $([string]$Report.group_by))"
            }
            $lines.Add($title)
            $lines.Add('')
            if (@($Report.rows).Count -eq 0) {
                $lines.Add('_No dated events matched the selected filters._')
            }
            elseif (-not [string]::IsNullOrWhiteSpace([string]$Report.group_by)) {
                $columns = @('Date') + @($Report.columns)
                $lines.Add('| ' + ($columns -join ' | ') + ' |')
                $lines.Add('|' + (@($columns | ForEach-Object { '-' * ($_.Length + 2) }) -join '|') + '|')
                foreach ($row in @($Report.rows)) {
                    $values = @([string]$row.date)
                    foreach ($column in @($Report.columns)) {
                        $values += [string]$row.$column
                    }
                    $lines.Add('| ' + ($values -join ' | ') + ' |')
                }
            }
            else {
                $lines.Add('| Date | Count |')
                $lines.Add('|------|-------|')
                foreach ($row in @($Report.rows)) {
                    $lines.Add("| $([string]$row.date) | $([int]$row.count) |")
                }
            }
        }
    }
    return ($lines -join [Environment]::NewLine)
}

if ($ScanDirs.Count -gt 0) {
    $eventFiles = @(Find-FrictionEventsFiles -ScanDirs $ScanDirs)
    if ($eventFiles.Count -eq 0) {
        throw "No events.jsonl files found under: $($ScanDirs -join ', ')"
    }
}
else {
    $paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile
    $EventsFile = $paths.EventsFile
    if (-not (Test-Path -LiteralPath $EventsFile)) {
        throw "Events file not found: $EventsFile"
    }
    $eventFiles = @($EventsFile)
}

if ($ReportType -eq 'index' -and $eventFiles.Count -ne 1) {
    throw '-ReportType index requires exactly one events file'
}

$events = [System.Collections.Generic.List[object]]::new()
$repoBuckets = @{}
foreach ($file in $eventFiles) {
    foreach ($event in (Import-Events $file)) {
        $repoRootValue = Get-RepoRootFromEventsFile $file
        Add-Member -InputObject $event -MemberType NoteProperty -Name '_events_file' -Value $file -Force
        Add-Member -InputObject $event -MemberType NoteProperty -Name '_repo_root' -Value ([string](Get-EventFieldValue -event $event -Name 'repo_root' -Default '')) -Force
        if ([string]::IsNullOrWhiteSpace([string]$event._repo_root)) {
            $event._repo_root = $repoRootValue
        }
        if (-not (Test-EventMatchesFilters $event)) { continue }
        $events.Add($event) | Out-Null
        if (-not $repoBuckets.ContainsKey($file)) {
            $repoBuckets[$file] = [System.Collections.Generic.List[object]]::new()
        }
        $repoBuckets[$file].Add($event) | Out-Null
    }
}

$sortedEvents = @($events | Sort-Object -Property @{ Expression = { [string](Get-EventFieldValue -event $_ -Name 'recorded_at' -Default '') }; Descending = $false }, @{ Expression = { [string](Get-EventFieldValue -event $_ -Name 'event_id' -Default '') }; Descending = $false })
$repoSummaries = @(
    foreach ($file in @($repoBuckets.Keys | Sort-Object)) {
        Get-RepoSummary -EventsFilePath $file -Events @($repoBuckets[$file])
    }
)
$generated = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss') + ' UTC'

switch ($ReportType) {
    'index' {
        $summary = Get-RepoSummary -EventsFilePath $eventFiles[0] -Events $sortedEvents
        $report = [pscustomobject]@{
            report_type        = 'index'
            index_rebuilt      = $generated
            repo_root          = $summary.repo_root
            events_file        = $summary.events_file
            entries            = $summary.entries
            blocked            = $summary.blocked
            earliest_event     = $summary.earliest_event
            latest_event       = $summary.latest_event
            events_list        = @($summary.events_list)
            recurring_patterns = @($summary.recurring_patterns)
            alias_counts       = @($summary.alias_counts)
            source_counts      = @($summary.source_counts)
            tag_counts         = @($summary.tag_counts)
            date_counts        = @($summary.date_counts)
        }
    }
    'cross-repo' {
        $report = [pscustomobject]@{
            report_type        = 'cross-repo'
            index_rebuilt      = $generated
            repos_scanned      = $repoSummaries.Count
            total_entries      = $sortedEvents.Count
            repos              = @(
                foreach ($summary in $repoSummaries) {
                    [pscustomobject]@{
                        repo_root   = $summary.repo_root
                        events_file = $summary.events_file
                        entries     = $summary.entries
                    }
                }
            )
            impact_summary     = Convert-CounterToRows -Counter (Get-ImpactCounts $sortedEvents)
            alias_counts       = @(Get-AliasCounts $sortedEvents | ForEach-Object {
                [pscustomobject]@{
                    value   = $_.value
                    count   = $_.count
                    percent = Get-PercentString -Count $_.count -Total $sortedEvents.Count
                }
            })
            tag_counts         = Convert-CounterToRows -Counter (Get-TagCounts $sortedEvents) -Total $sortedEvents.Count -WithPercent
            fingerprint_counts = Convert-CounterToRows -Counter (Get-FingerprintCounts $sortedEvents) -Limit 10
        }
    }
    'per-repo' {
        $report = [pscustomobject]@{
            report_type    = 'per-repo'
            index_rebuilt  = $generated
            repos          = $repoSummaries.Count
            total_entries  = $sortedEvents.Count
            repo_summaries = $repoSummaries
        }
    }
    'timeseries' {
        $rows = @{}
        foreach ($event in $sortedEvents) {
            $ts = [string](Get-EventFieldValue -event $event -Name 'recorded_at' -Default '')
            if ([string]::IsNullOrWhiteSpace($ts) -or $ts.Length -lt 10) { continue }
            $eventDate = $ts.Substring(0, 10)
            if (-not $rows.ContainsKey($eventDate)) {
                $rows[$eventDate] = @{}
            }
            if ([string]::IsNullOrWhiteSpace($GroupBy)) {
                Add-CounterValue -Counter $rows[$eventDate] -Key 'count'
                continue
            }
            $values = switch ($GroupBy) {
                'impact' { @([string](Get-EventFieldValue -event $event -Name 'impact' -Default '')) }
                'alias'  { @(Get-EventAliases $event) }
                'tag'    { @(Get-EventTags $event) }
            }
            foreach ($value in $values | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) {
                Add-CounterValue -Counter $rows[$eventDate] -Key ([string]$value)
            }
        }
        $allColumns = @()
        if (-not [string]::IsNullOrWhiteSpace($GroupBy)) {
            $allColumns = @($rows.Values | ForEach-Object { $_.Keys } | Sort-Object -Unique)
        }
        $dataRows = @(
            foreach ($dateKey in @($rows.Keys | Sort-Object)) {
                if ([string]::IsNullOrWhiteSpace($GroupBy)) {
                    [pscustomobject]@{
                        date  = $dateKey
                        count = [int]$rows[$dateKey]['count']
                    }
                }
                else {
                    $row = [ordered]@{ date = $dateKey }
                    foreach ($column in $allColumns) {
                        $row[$column] = [int](Get-ValueOrFallback $rows[$dateKey][$column] 0)
                    }
                    [pscustomobject]$row
                }
            }
        )
        $report = [pscustomobject]@{
            report_type   = 'timeseries'
            index_rebuilt = $generated
            group_by      = $GroupBy
            columns       = $allColumns
            rows          = $dataRows
        }
    }
}

$result = switch ($Format) {
    'json' { $report | ConvertTo-Json -Depth 8 }
    'md'   { Render-MarkdownReport $report }
}

if (-not [string]::IsNullOrWhiteSpace($Output)) {
    [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($Output), $result + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}
else {
    Write-Output $result
}
