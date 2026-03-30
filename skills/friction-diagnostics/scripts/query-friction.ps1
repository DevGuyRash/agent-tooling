param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string[]]$ScanDirs = @(),
    [string]$Category = '',
    [string]$Surface = '',
    [string]$Mode = '',
    [string]$RunEffect = '',
    [string]$Fingerprint = '',
    [string]$AgentKind = '',
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
    [ValidateSet('jsonl', 'json', 'md')][string]$Format = 'jsonl',
    [string]$Output = '',
    [switch]$Compact,
    [switch]$SuggestTags,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/query-friction.ps1 [-EventsFile PATH | -ScanDirs DIR [DIR...]] [filters]

Input:
  -EventsFile PATH          Single events file (default: auto-detected)
  -ScanDirs DIR [DIR...]    Recursively discover all events.jsonl files under
                            the given directories matching
                            */.local*/reports/friction/events.jsonl

Filters:
  -Category VALUE
  -Surface VALUE
  -Mode VALUE
  -RunEffect VALUE
  -Fingerprint VALUE
  -AgentKind VALUE
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
  -After ISO-TIMESTAMP      Filter events with recorded_at > TIMESTAMP
  -SourceRef PATH

Output:
  -Format jsonl|json|md
  -Output PATH
  -Compact                  Strip empty-string and null fields (json/jsonl only)
  -SuggestTags
  -Help
"@
    exit 0
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

function Import-MultipleEvents {
    param([string[]]$FilePaths)
    $allEvents = [System.Collections.Generic.List[object]]::new()
    foreach ($fp in $FilePaths) {
        if (-not (Test-Path -LiteralPath $fp)) { continue }
        foreach ($ev in @(Import-Events $fp)) {
            $null = $allEvents.Add($ev)
        }
    }
    # Sort by recorded_at
    return @($allEvents | Sort-Object { [string](Get-EventFieldValue -event $_ -Name 'recorded_at' -Default '') })
}

# Resolve input files
if ($ScanDirs.Count -gt 0) {
    $discovered = @()
    foreach ($dir in $ScanDirs) {
        $found = Get-ChildItem -Path $dir -Recurse -Filter 'events.jsonl' -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '[/\\]\.local[^/\\]*[/\\]reports[/\\]friction[/\\]events\.jsonl$' } |
            ForEach-Object { $_.FullName }
        $discovered += $found
    }
    if ($discovered.Count -eq 0) {
        throw "No events.jsonl files found under: $($ScanDirs -join ', ')"
    }
    $events = Import-MultipleEvents -FilePaths $discovered
} else {
    $paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile
    $EventsFile = $paths.EventsFile
    if (-not (Test-Path -LiteralPath $EventsFile)) {
        throw "Events file not found: $EventsFile"
    }
    $events = Import-MultipleEvents -FilePaths @($EventsFile)
}

# Helper: get tags from an event
function Get-EventTags {
    param($event)
    $tags = Get-EventFieldValue -event $event -Name 'tags'
    if ($null -eq $tags) { return @() }
    return @(@($tags) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ })
}

# Helper: check if an event matches a source ref
function Test-SourceRefMatch {
    param($event, [string]$ref)
    $sources = Get-EventFieldValue -event $event -Name 'sources'
    if ($null -ne $sources) {
        foreach ($s in @($sources)) {
            if ($null -ne $s -and [string]$s.ref -eq $ref) { return $true }
        }
    }
    return $false
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

if ($SuggestTags) {
    $tagsSet = [System.Collections.Generic.SortedSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($event in $events) {
        foreach ($tag in (Get-EventTags $event)) {
            $null = $tagsSet.Add($tag)
        }
    }
    $result = $tagsSet -join [Environment]::NewLine
    if (-not [string]::IsNullOrWhiteSpace($Output)) {
        [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($Output), $result + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    }
    else {
        Write-Output $result
    }
    exit 0
}

$filtered = foreach ($event in $events) {
    $ts = [string](Get-EventFieldValue -event $event -Name 'recorded_at' -Default '')
    $eventDate = ''
    if (-not [string]::IsNullOrWhiteSpace($ts) -and $ts.Length -ge 10) {
        $eventDate = $ts.Substring(0, 10)
    }
    $categoryParts = Get-DerivedCategoryParts $event
    $confidenceValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'confidence')
    $guidanceValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'guidance_quality')
    $exitCodeValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'exit_code')

    if (-not [string]::IsNullOrWhiteSpace($Category) -and [string](Get-EventFieldValue -event $event -Name 'derived_category' -Default '') -ne $Category) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Surface) -and $categoryParts[0] -ne $Surface) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Mode) -and $categoryParts[1] -ne $Mode) { continue }
    if (-not [string]::IsNullOrWhiteSpace($RunEffect) -and $categoryParts[2] -ne $RunEffect) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Fingerprint) -and [string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default '') -ne $Fingerprint) { continue }
    if (-not [string]::IsNullOrWhiteSpace($AgentKind) -and [string](Get-EventFieldValue -event $event -Name 'agent_kind' -Default '') -ne $AgentKind) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Role) -and [string](Get-EventFieldValue -event $event -Name 'role' -Default '') -ne $Role) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Tag) -and (Get-EventTags $event) -notcontains $Tag) { continue }
    if (-not (Test-TextMatch $event $Text)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ConfidenceMin) -and ($null -eq $confidenceValue -or $confidenceValue -lt [int]$ConfidenceMin)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ConfidenceMax) -and ($null -eq $confidenceValue -or $confidenceValue -gt [int]$ConfidenceMax)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($GuidanceMin) -and ($null -eq $guidanceValue -or $guidanceValue -lt [int]$GuidanceMin)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($GuidanceMax) -and ($null -eq $guidanceValue -or $guidanceValue -gt [int]$GuidanceMax)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ExitCode) -and ($null -eq $exitCodeValue -or $exitCodeValue -ne [int]$ExitCode)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ToolName) -and [string](Get-EventFieldValue -event $event -Name 'tool_name' -Default '') -ne $ToolName) { continue }
    if (-not [string]::IsNullOrWhiteSpace($OwnerHint) -and [string](Get-EventFieldValue -event $event -Name 'owner_hint' -Default '') -ne $OwnerHint) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ComponentHint) -and [string](Get-EventFieldValue -event $event -Name 'component_hint' -Default '') -ne $ComponentHint) { continue }
    if ($Workaround -and -not [bool](Get-EventFieldValue -event $event -Name 'workaround_used' -Default $false)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Date) -and $eventDate -ne $Date) { continue }
    if (-not [string]::IsNullOrWhiteSpace($DateFrom) -and -not [string]::IsNullOrWhiteSpace($eventDate) -and $eventDate -lt $DateFrom) { continue }
    if (-not [string]::IsNullOrWhiteSpace($DateTo) -and -not [string]::IsNullOrWhiteSpace($eventDate) -and $eventDate -gt $DateTo) { continue }
    if (-not [string]::IsNullOrWhiteSpace($After) -and -not [string]::IsNullOrWhiteSpace($ts) -and $ts -le $After) { continue }

    if (-not [string]::IsNullOrWhiteSpace($SourceRef)) {
        if (-not (Test-SourceRefMatch $event $SourceRef)) { continue }
    }

    $event
}

switch ($Format) {
    'jsonl' {
        $result = @($filtered | ForEach-Object {
            $ev = $_
            if ($Compact) { $ev = Remove-EmptyFields $ev }
            $ev | ConvertTo-Json -Compress -Depth 8
        }) -join [Environment]::NewLine
    }
    'json' {
        if ($Compact) {
            $compacted = @($filtered | ForEach-Object { Remove-EmptyFields $_ })
            $result = $compacted | ConvertTo-Json -Depth 8
        } else {
            $result = @($filtered) | ConvertTo-Json -Depth 8
        }
    }
    'md' {
        $lines = [System.Collections.Generic.List[string]]::new()
        $lines.Add('# Friction Query Results')
        $lines.Add('')
        $lines.Add("- Entries: $(@($filtered).Count)")
        $lines.Add('')
        foreach ($event in $filtered) {
            $lines.Add("## $([string](Get-EventFieldValue -event $event -Name 'event_id' -Default '')): $([string](Get-EventFieldValue -event $event -Name 'title' -Default ''))")
            $lines.Add('')
            $lines.Add("- Recorded: $([string](Get-EventFieldValue -event $event -Name 'recorded_at' -Default ''))")
            $lines.Add("- Category: $([string](Get-EventFieldValue -event $event -Name 'derived_category' -Default ''))")
            $lines.Add("- Fingerprint: $([string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default ''))")
            if ([string](Get-EventFieldValue -event $event -Name 'provenance_source' -Default '') -eq 'explicit') {
                $lines.Add("- Agent: $([string](Get-EventFieldValue -event $event -Name 'agent_name' -Default ''))")
                $lines.Add("- Agent kind: $([string](Get-EventFieldValue -event $event -Name 'agent_kind' -Default ''))")
                $lines.Add("- Role: $([string](Get-EventFieldValue -event $event -Name 'role' -Default ''))")
            }
            $sources = Get-EventFieldValue -event $event -Name 'sources'
            if ($null -ne $sources -and $sources -is [System.Array] -and $sources.Count -gt 0) {
                $refs = @($sources | Where-Object { $null -ne $_ } | ForEach-Object { [string]$_.ref } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
                if ($refs.Count -gt 0) {
                    $lines.Add("- Sources: $($refs -join ', ')")
                }
            }
            $tags = Get-EventTags $event
            if ($tags.Count -gt 0) {
                $lines.Add("- Tags: $($tags -join ', ')")
            }
            $lines.Add("- Actual outcome: $([string](Get-EventFieldValue -event $event -Name 'actual_outcome' -Default ''))")
            $lines.Add('')
        }
        $result = $lines -join [Environment]::NewLine
    }
}

if (-not [string]::IsNullOrWhiteSpace($Output)) {
    [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($Output), $result + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}
else {
    Write-Output $result
}
