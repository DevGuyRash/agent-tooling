param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string[]]$ScanDirs = @(),
    [string]$Category = '',
    [string]$Surface = '',
    [string]$Mode = '',
    [string]$RunEffect = '',
    [string]$Fingerprint = '',
    [string]$Role = '',
    [string]$Tag = '',
    [string]$Text = '',
    [string]$ConfidenceMin = '',
    [string]$ConfidenceMax = '',
    [string]$GuidanceMin = '',
    [string]$GuidanceMax = '',
    [string]$ExitCode = '',
    [string]$ToolName = '',
    [string]$OwnerHint = '',
    [string]$ComponentHint = '',
    [switch]$Workaround,
    [string]$Date = '',
    [string]$DateFrom = '',
    [string]$DateTo = '',
    [string]$After = '',
    [string]$SourceRef = '',
    [ValidateSet('index', 'cross-repo', 'per-repo', 'timeseries')][string]$ReportType = 'index',
    [ValidateSet('', 'surface', 'mode', 'run_effect', 'category', 'tag')][string]$GroupBy = '',
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
  -Category VALUE
  -Surface VALUE
  -Mode VALUE
  -RunEffect VALUE
  -Fingerprint VALUE
  -Role VALUE
  -Tag VALUE               Single tag filter; repeat support is not implemented
  -Text PATTERN            Case-insensitive substring search across narrative fields
  -ConfidenceMin N
  -ConfidenceMax N
  -GuidanceMin N
  -GuidanceMax N
  -ExitCode N
  -ToolName VALUE
  -OwnerHint VALUE
  -ComponentHint VALUE
  -Workaround              Only include events with workaround_used=true
  -Date YYYY-MM-DD
  -DateFrom YYYY-MM-DD
  -DateTo YYYY-MM-DD
  -After ISO-TIMESTAMP     Filter events with recorded_at > TIMESTAMP
  -SourceRef PATH

Report:
  -ReportType index|cross-repo|per-repo|timeseries
  -GroupBy surface|mode|run_effect|category|tag
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

function Remove-EmptyFields {
    param($event)
    $toRemove = @($event.PSObject.Properties | Where-Object {
        $null -eq $_.Value -or ([string]$_.Value -eq '' -and $_.Value -isnot [System.Array] -and $_.Value -isnot [PSCustomObject])
    } | ForEach-Object { $_.Name })
    foreach ($name in $toRemove) {
        $event.PSObject.Properties.Remove($name)
    }
    return $event
}

function Get-EventFieldValue {
    param(
        $event,
        [string]$Name,
        $Default = $null
    )

    $prop = $event.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    return $prop.Value
}

function Get-EventTags {
    param($event)
    $tags = Get-EventFieldValue -event $event -Name 'tags'
    if ($null -eq $tags) { return @() }
    return @(@($tags) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ })
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

function Get-DerivedCategoryParts {
    param($event)
    $value = [string](Get-EventFieldValue -event $event -Name 'derived_category' -Default '')
    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        $parts = @($value.Split('/', 3))
    }
    while ($parts.Count -lt 3) {
        $parts += ''
    }
    return $parts
}

function Get-NullableInt {
    param($value)
    if ($null -eq $value) { return $null }
    $text = [string]$value
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    if ($text -notmatch '^-?\d+$') { return $null }
    return [int]$text
}

function Test-TextMatch {
    param($event, [string]$query)
    if ([string]::IsNullOrWhiteSpace($query)) { return $true }
    $needle = $query.ToLowerInvariant()
    foreach ($field in @('title', 'actual_outcome', 'action_taken', 'reading', 'hindsight')) {
        $value = [string](Get-EventFieldValue -event $event -Name $field -Default '')
        if ($value.ToLowerInvariant().Contains($needle)) {
            return $true
        }
    }
    return $false
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

function Get-CategoryCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        Add-CounterValue -Counter $counter -Key ([string](Get-EventFieldValue -event $event -Name 'derived_category' -Default ''))
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

function Get-RunEffectCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        $parts = Get-DerivedCategoryParts $event
        Add-CounterValue -Counter $counter -Key $parts[2]
    }
    return $counter
}

function Get-RunEffectRows {
    param([object[]]$Events)
    return @(Convert-CounterToRows -Counter (Get-RunEffectCounts $Events))
}

function Get-WorkaroundRate {
    param([object[]]$Events)
    $used = 0
    foreach ($event in $Events) {
        $val = Get-EventFieldValue -event $event -Name 'workaround_used' -Default $false
        if ($val -eq $true) { $used++ }
    }
    return [pscustomobject]@{ used = $used; total = $Events.Count }
}

function Get-NumericDist {
    param([object[]]$Events, [string]$FieldName, [switch]$AllowZero)
    $values = @(foreach ($event in $Events) {
        $v = Get-NullableInt (Get-EventFieldValue -event $event -Name $FieldName)
        if ($null -ne $v) {
            if ($AllowZero -or $v -gt 0) { $v }
        }
    })
    if ($values.Count -eq 0) { return $null }
    $sorted = @($values | Sort-Object)
    if ($sorted.Count % 2 -eq 1) {
        $median = $sorted[[int]($sorted.Count / 2)]
    } else {
        $median = [int](($sorted[$sorted.Count / 2 - 1] + $sorted[$sorted.Count / 2]) / 2)
    }
    return [pscustomobject]@{
        min    = $sorted[0]
        max    = $sorted[-1]
        median = $median
        count  = $sorted.Count
    }
}

function Get-ToolCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        Add-CounterValue -Counter $counter -Key ([string](Get-EventFieldValue -event $event -Name 'tool_name' -Default ''))
    }
    return $counter
}

function Get-ComponentCounts {
    param([object[]]$Events)
    $counter = @{}
    foreach ($event in $Events) {
        Add-CounterValue -Counter $counter -Key ([string](Get-EventFieldValue -event $event -Name 'component_hint' -Default ''))
    }
    return $counter
}

function Test-EventMatchesFilters {
    param($event)
    $ts = [string](Get-EventFieldValue -event $event -Name 'recorded_at' -Default '')
    $eventDate = ''
    if (-not [string]::IsNullOrWhiteSpace($ts) -and $ts.Length -ge 10) {
        $eventDate = $ts.Substring(0, 10)
    }
    $categoryParts = Get-DerivedCategoryParts $event
    $confidenceValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'confidence')
    $guidanceValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'guidance_quality')
    $exitCodeValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'exit_code')

    if (-not [string]::IsNullOrWhiteSpace($Category) -and [string](Get-EventFieldValue -event $event -Name 'derived_category' -Default '') -ne $Category) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($Surface) -and $categoryParts[0] -ne $Surface) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($Mode) -and $categoryParts[1] -ne $Mode) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($RunEffect) -and $categoryParts[2] -ne $RunEffect) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($Fingerprint) -and [string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default '') -ne $Fingerprint) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($Role) -and [string](Get-EventFieldValue -event $event -Name 'role' -Default '') -ne $Role) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($Tag) -and (Get-EventTags $event) -notcontains $Tag) { return $false }
    if (-not (Test-TextMatch $event $Text)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($ConfidenceMin) -and ($null -eq $confidenceValue -or $confidenceValue -lt [int]$ConfidenceMin)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($ConfidenceMax) -and ($null -eq $confidenceValue -or $confidenceValue -gt [int]$ConfidenceMax)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($GuidanceMin) -and ($null -eq $guidanceValue -or $guidanceValue -lt [int]$GuidanceMin)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($GuidanceMax) -and ($null -eq $guidanceValue -or $guidanceValue -gt [int]$GuidanceMax)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($ExitCode) -and ($null -eq $exitCodeValue -or $exitCodeValue -ne [int]$ExitCode)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($ToolName) -and [string](Get-EventFieldValue -event $event -Name 'tool_name' -Default '') -ne $ToolName) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($OwnerHint) -and [string](Get-EventFieldValue -event $event -Name 'owner_hint' -Default '') -ne $OwnerHint) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($ComponentHint) -and [string](Get-EventFieldValue -event $event -Name 'component_hint' -Default '') -ne $ComponentHint) { return $false }
    if ($Workaround -and -not [bool](Get-EventFieldValue -event $event -Name 'workaround_used' -Default $false)) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($Date) -and $eventDate -ne $Date) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($DateFrom) -and -not [string]::IsNullOrWhiteSpace($eventDate) -and $eventDate -lt $DateFrom) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($DateTo) -and -not [string]::IsNullOrWhiteSpace($eventDate) -and $eventDate -gt $DateTo) { return $false }
    if (-not [string]::IsNullOrWhiteSpace($After) -and -not [string]::IsNullOrWhiteSpace($ts) -and $ts -le $After) { return $false }
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
    $earliest = if ($entries -gt 0) { [string](Get-EventFieldValue -event $sortedEvents[0] -Name 'recorded_at' -Default '') } else { '' }
    $latest = if ($entries -gt 0) { [string](Get-EventFieldValue -event $sortedEvents[-1] -Name 'recorded_at' -Default '') } else { '' }
    [pscustomobject]@{
        repo_root = $repoRootValue
        events_file = $EventsFilePath
        events_file_display = Get-RelativeEventsFile -RepoRoot $repoRootValue -Path $EventsFilePath
        entries = $entries
        earliest_event = $earliest
        latest_event = $latest
        category_counts = Convert-CounterToRows -Counter (Get-CategoryCounts $sortedEvents) -Total $entries -WithPercent
        fingerprint_counts = Convert-CounterToRows -Counter (Get-FingerprintCounts $sortedEvents) -Limit 10
        date_counts = Convert-CounterToRows -Counter (Get-DateCounts $sortedEvents) -SortByValue
        tag_counts = Convert-CounterToRows -Counter (Get-TagCounts $sortedEvents) -Total $entries -WithPercent
        top_sources = Convert-CounterToRows -Counter (Get-SourceCounts $sortedEvents) -Limit 10
        run_effect_summary = Get-RunEffectRows $sortedEvents
    }
}

function Get-MarkdownLinesForRows {
    param(
        [object[]]$Rows,
        [string]$EmptyMessage,
        [switch]$WithPercent,
        [string]$Suffix = ''
    )
    if (@($Rows).Count -eq 0) {
        return @($EmptyMessage)
    }
    return @(
        foreach ($row in $Rows) {
            if ($WithPercent) {
                "- ``$([string]$row.value)`` - $([int]$row.count) ($([string]$row.percent))"
            }
            else {
                "- ``$([string]$row.value)`` - $([int]$row.count)$Suffix"
            }
        }
    )
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
            $lines.Add('# Friction Index')
            $lines.Add('')
            $lines.Add("**Index rebuilt:** $([string]$Report.index_rebuilt)")
            $lines.Add("**Events file:** $([string]$Report.events_file)")
            if (-not [string]::IsNullOrWhiteSpace([string]$Report.repo_root)) {
                $lines.Add("**Repo root:** $([string]$Report.repo_root)")
            }
            $lines.Add("**Entries:** $([int]$Report.entries)")
            $lines.Add("**Earliest event:** $([string](Get-ValueOrFallback $Report.earliest_event '(not available)'))")
            $lines.Add("**Latest event:** $([string](Get-ValueOrFallback $Report.latest_event '(not available)'))")
            $lines.Add('')
            $lines.Add('## Category Counts')
            $lines.Add('')
            $catRows = @(@($Report.category_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.percent) })
            $lines.Add((Format-MarkdownTable -Headers @('Category', 'Count', '%') -Rows $catRows -EmptyMessage '_No categorized events._'))
            $lines.Add('')
            $lines.Add('## Top Fingerprints')
            $lines.Add('')
            foreach ($line in (Get-MarkdownLinesForRows -Rows @($Report.fingerprint_counts) -EmptyMessage '_No fingerprints yet._' -Suffix ' events')) { $lines.Add($line) }
            $lines.Add('')
            $lines.Add('## Date Counts')
            $lines.Add('')
            $dateRows = @(@($Report.date_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Date', 'Count') -Rows $dateRows -EmptyMessage '_No date counts available._'))
            $lines.Add('')
            $lines.Add('## Tags')
            $lines.Add('')
            $tagRows = @(@($Report.tag_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.percent) })
            $lines.Add((Format-MarkdownTable -Headers @('Tag', 'Events', '% of events') -Rows $tagRows -EmptyMessage '_No tags recorded._'))
            $lines.Add('')
            $lines.Add('## Top Sources')
            $lines.Add('')
            foreach ($line in (Get-MarkdownLinesForRows -Rows @($Report.top_sources) -EmptyMessage '_No sources recorded._')) { $lines.Add($line) }
            $lines.Add('')
            $lines.Add('## Run Effect Summary')
            $lines.Add('')
            $reRows = @(@($Report.run_effect_summary) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Effect', 'Count') -Rows $reRows -EmptyMessage '_No run effects recorded._'))
            $lines.Add('')
            $lines.Add('## Workaround Rate')
            $lines.Add('')
            if ($null -eq $Report.workaround_rate -or [int]$Report.workaround_rate.total -le 0) {
                $lines.Add('_No events._')
            }
            else {
                $waUsed = [int]$Report.workaround_rate.used
                $waTotal = [int]$Report.workaround_rate.total
                $waPct = Get-PercentString -Count $waUsed -Total $waTotal
                $lines.Add("$waUsed of $waTotal events ($waPct) used workarounds")
            }
            $lines.Add('')
            $lines.Add('## Confidence')
            $lines.Add('')
            if ($null -eq $Report.confidence_dist) {
                $lines.Add('_No confidence values recorded._')
            }
            else {
                $cd = $Report.confidence_dist
                $lines.Add("$([int]$cd.min) / $([int]$cd.median) / $([int]$cd.max) ($([int]$cd.count) events with confidence)")
            }
            $lines.Add('')
            $lines.Add('## Guidance Quality')
            $lines.Add('')
            if ($null -eq $Report.guidance_dist) {
                $lines.Add('_No guidance_quality values recorded._')
            }
            else {
                $gd = $Report.guidance_dist
                $lines.Add("$([int]$gd.min) / $([int]$gd.median) / $([int]$gd.max) ($([int]$gd.count) events with guidance_quality)")
            }
            $lines.Add('')
            $lines.Add('## Top Tools')
            $lines.Add('')
            $toolRows = @(@($Report.tool_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Tool', 'Count') -Rows $toolRows -EmptyMessage '_No tool_name values recorded._'))
            $lines.Add('')
            $lines.Add('## Top Components')
            $lines.Add('')
            $compRows = @(@($Report.component_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Component', 'Count') -Rows $compRows -EmptyMessage '_No component_hint values recorded._'))
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
                $lines.Add('_No repos matched the selected filters._')
            }
            else {
                foreach ($repo in @($Report.repos)) {
                    $label = if (-not [string]::IsNullOrWhiteSpace([string]$repo.repo_root)) { [string]$repo.repo_root } else { [string]$repo.events_file }
                    $lines.Add("- ``$label`` - $([int]$repo.entries) events")
                }
            }
            $lines.Add('')
            $lines.Add('## Category Counts (all repos)')
            $lines.Add('')
            $catRows = @(@($Report.category_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.percent) })
            $lines.Add((Format-MarkdownTable -Headers @('Category', 'Count', '%') -Rows $catRows -EmptyMessage '_No categorized events._'))
            $lines.Add('')
            $lines.Add('## Top Fingerprints (all repos)')
            $lines.Add('')
            foreach ($line in (Get-MarkdownLinesForRows -Rows @($Report.fingerprint_counts) -EmptyMessage '_No fingerprints yet._' -Suffix ' events')) { $lines.Add($line) }
            $lines.Add('')
            $lines.Add('## Run Effect Summary')
            $lines.Add('')
            $reRows = @(@($Report.run_effect_summary) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
            $lines.Add((Format-MarkdownTable -Headers @('Effect', 'Count') -Rows $reRows -EmptyMessage '_No run effects recorded._'))
            $lines.Add('')
            $lines.Add('## Tags')
            $lines.Add('')
            $tagRows = @(@($Report.tag_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.percent) })
            $lines.Add((Format-MarkdownTable -Headers @('Tag', 'Count', '%') -Rows $tagRows -EmptyMessage '_No tags recorded._'))
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
                    $lines.Add("**Events file:** $([string]$repo.events_file_display)")
                    $lines.Add("**Entries:** $([int]$repo.entries) | **Earliest event:** $([string](Get-ValueOrFallback $repo.earliest_event '(not available)')) | **Latest event:** $([string](Get-ValueOrFallback $repo.latest_event '(not available)'))")
                    $lines.Add('')
                    $lines.Add('### Category Counts')
                    $lines.Add('')
                    $repoCatRows = @(@($repo.category_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.percent) })
                    $lines.Add((Format-MarkdownTable -Headers @('Category', 'Count', '%') -Rows $repoCatRows -EmptyMessage '_No categorized events._'))
                    $lines.Add('')
                    $lines.Add('### Top Fingerprints')
                    $lines.Add('')
                    foreach ($line in (Get-MarkdownLinesForRows -Rows @($repo.fingerprint_counts) -EmptyMessage '_No fingerprints yet._' -Suffix ' events')) { $lines.Add($line) }
                    $lines.Add('')
                    $lines.Add('### Run Effect Summary')
                    $lines.Add('')
                    $repoReRows = @(@($repo.run_effect_summary) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count) })
                    $lines.Add((Format-MarkdownTable -Headers @('Effect', 'Count') -Rows $repoReRows -EmptyMessage '_No run effects recorded._'))
                    $lines.Add('')
                    $lines.Add('### Tags')
                    $lines.Add('')
                    $repoTagRows = @(@($repo.tag_counts) | ForEach-Object { [string[]]@([string]$_.value, [string]$_.count, [string]$_.percent) })
                    $lines.Add((Format-MarkdownTable -Headers @('Tag', 'Count', '%') -Rows $repoTagRows -EmptyMessage '_No tags recorded._'))
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
            report_type = 'index'
            index_rebuilt = $generated
            repo_root = $summary.repo_root
            events_file = $summary.events_file
            entries = $summary.entries
            earliest_event = $summary.earliest_event
            latest_event = $summary.latest_event
            category_counts = @($summary.category_counts)
            fingerprint_counts = @($summary.fingerprint_counts)
            date_counts = @($summary.date_counts)
            tag_counts = @($summary.tag_counts)
            top_sources = @($summary.top_sources)
            run_effect_summary = @($summary.run_effect_summary)
            workaround_rate = Get-WorkaroundRate $sortedEvents
            confidence_dist = Get-NumericDist -Events $sortedEvents -FieldName 'confidence'
            guidance_dist = Get-NumericDist -Events $sortedEvents -FieldName 'guidance_quality' -AllowZero
            tool_counts = Convert-CounterToRows -Counter (Get-ToolCounts $sortedEvents) -Limit 5
            component_counts = Convert-CounterToRows -Counter (Get-ComponentCounts $sortedEvents) -Limit 5
        }
    }
    'cross-repo' {
        $report = [pscustomobject]@{
            report_type = 'cross-repo'
            index_rebuilt = $generated
            repos_scanned = $repoSummaries.Count
            total_entries = $sortedEvents.Count
            repos = @(
                foreach ($summary in $repoSummaries) {
                    [pscustomobject]@{
                        repo_root = $summary.repo_root
                        events_file = $summary.events_file
                        entries = $summary.entries
                    }
                }
            )
            category_counts = Convert-CounterToRows -Counter (Get-CategoryCounts $sortedEvents) -Total $sortedEvents.Count -WithPercent
            fingerprint_counts = Convert-CounterToRows -Counter (Get-FingerprintCounts $sortedEvents) -Limit 10
            run_effect_summary = Get-RunEffectRows $sortedEvents
            tag_counts = Convert-CounterToRows -Counter (Get-TagCounts $sortedEvents) -Total $sortedEvents.Count -WithPercent
        }
    }
    'per-repo' {
        $report = [pscustomobject]@{
            report_type = 'per-repo'
            index_rebuilt = $generated
            repos = $repoSummaries.Count
            total_entries = $sortedEvents.Count
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
                'surface' { @((Get-DerivedCategoryParts $event)[0]) }
                'mode' { @((Get-DerivedCategoryParts $event)[1]) }
                'run_effect' { @((Get-DerivedCategoryParts $event)[2]) }
                'category' { @([string](Get-EventFieldValue -event $event -Name 'derived_category' -Default '')) }
                'tag' { @(Get-EventTags $event) }
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
                        date = $dateKey
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
            report_type = 'timeseries'
            index_rebuilt = $generated
            group_by = $GroupBy
            columns = $allColumns
            rows = $dataRows
        }
    }
}

$result = switch ($Format) {
    'json' { $report | ConvertTo-Json -Depth 8 }
    'md' { Render-MarkdownReport $report }
}

if (-not [string]::IsNullOrWhiteSpace($Output)) {
    [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($Output), $result + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}
else {
    Write-Output $result
}
