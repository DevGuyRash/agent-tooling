Set-StrictMode -Version Latest

# --- Schema SSOT ---
# All field definitions live in friction-event-schema.json.
# Scripts load it once and derive field lists from x- metadata.
$script:SCHEMA_FILE = if ($env:SCHEMA_FILE) { $env:SCHEMA_FILE } else {
    Join-Path (Split-Path -Parent (Split-Path -Parent $PSCommandPath)) 'friction-event-schema.json'
}
$script:_SchemaCache = $null

function Get-EventSchema {
    if ($null -eq $script:_SchemaCache) {
        if (-not (Test-Path -LiteralPath $script:SCHEMA_FILE)) {
            throw "Schema file not found: $($script:SCHEMA_FILE)"
        }
        $script:_SchemaCache = Get-Content -LiteralPath $script:SCHEMA_FILE -Raw | ConvertFrom-Json -ErrorAction Stop
    }
    return $script:_SchemaCache
}

function Get-SchemaFieldsWhere {
    param([scriptblock]$Filter)
    $schema = Get-EventSchema
    $fields = @()
    foreach ($prop in $schema.properties.PSObject.Properties) {
        if (& $Filter $prop.Value) {
            $fields += $prop.Name
        }
    }
    return $fields
}

function Get-SchemaFieldProp {
    param(
        [string]$FieldName,
        [string]$PropName
    )
    $schema = Get-EventSchema
    $field = $schema.properties.PSObject.Properties[$FieldName]
    if ($null -eq $field) { return $null }
    $prop = $field.Value.PSObject.Properties[$PropName]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Get-SchemaMdRenderOrder {
    $schema = Get-EventSchema
    return @($schema.'x-render-md-order')
}

function Get-SchemaAggregateOrder {
    $schema = Get-EventSchema
    return @($schema.'x-aggregate-order')
}

function Get-SchemaSearchableFields {
    return Get-SchemaFieldsWhere { param($v) $v.'x-searchable' -eq $true }
}

function Get-SchemaAllFields {
    $schema = Get-EventSchema
    return @($schema.properties.PSObject.Properties.Name)
}

# Version constants derived from schema SSOT.
try {
    $schema = Get-EventSchema
    $script:SCHEMA_VERSION = if ($schema.'x-schema-version') { $schema.'x-schema-version' } else { '3.0.0' }
    $script:TAXONOMY_VERSION = if ($schema.'x-taxonomy-version') { $schema.'x-taxonomy-version' } else { '2.0.0' }
} catch {
    $script:SCHEMA_VERSION = '3.0.0'
    $script:TAXONOMY_VERSION = '2.0.0'
}

# Legacy compatibility: derive KNOWN_EVENT_KEYS from schema at load time.
# This will be removed once all scripts consume schema functions directly.
$script:KNOWN_EVENT_KEYS = @(
    'title', 'instruction_text', 'action_taken', 'expected_outcome',
    'actual_outcome', 'reading', 'hindsight', 'observed_surface',
    'surface', 'mode', 'run_effect', 'guidance_quality', 'confidence',
    'command', 'tool_name', 'exit_code', 'stderr', 'stdout_excerpt',
    'owner_hint', 'component_hint', 'workaround_used', 'workaround_note',
    'retries_lost', 'minutes_lost', 'fingerprint_key', 'tags',
    'agent_name', 'role', 'superproject_root', 'submodule_path',
    'sources'
)

function Get-Slug {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return 'friction-task' }
    $slug = $Text.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) { return 'friction-task' }
    return $slug
}

function Get-ShortSha256 {
    param(
        [string]$Text,
        [int]$Length = 8
    )
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha256.ComputeHash($bytes)
    }
    finally {
        $sha256.Dispose()
    }
    $hexCount = [Math]::Ceiling($Length / 2)
    return (-join ($hashBytes[0..($hexCount - 1)] | ForEach-Object { $_.ToString('x2') })).Substring(0, $Length)
}

function Get-BoundedSlug {
    param(
        [string]$Text,
        [int]$Limit = 255
    )
    $slug = Get-Slug $Text
    if ($slug.Length -le $Limit) { return $slug }

    $suffix = "-$(Get-ShortSha256 $slug)"
    $prefixLimit = $Limit - $suffix.Length
    if ($prefixLimit -lt 1) { $prefixLimit = 1 }
    $prefix = $slug.Substring(0, [Math]::Min($prefixLimit, $slug.Length)).TrimEnd('-')
    if ([string]::IsNullOrWhiteSpace($prefix)) { $prefix = 'friction-task' }
    return "$prefix$suffix"
}

function Add-CsvItem {
    param(
        [string]$List,
        [string]$Item
    )
    if ([string]::IsNullOrWhiteSpace($Item)) { return $List }
    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($List)) {
        $parts = $List.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    }
    if ($parts -contains $Item) { return ($parts -join ',') }
    $parts += $Item
    return ($parts -join ',')
}

function Get-FirstLine {
    param([string]$Text)
    if ($null -eq $Text) { return '' }
    return (($Text -split "`r?`n")[0])
}

function Get-TruncatedLine {
    param(
        [string]$Text,
        [int]$Limit = 80
    )
    $line = Get-FirstLine $Text
    if ($line.Length -le $Limit) { return $line }
    if ($Limit -lt 4) { return $line.Substring(0, 1) }
    return ($line.Substring(0, $Limit - 3) + '...')
}

function Get-TruncatedText {
    param(
        [string]$Text,
        [int]$Limit = 600
    )
    if ($null -eq $Text) { return '' }
    if ($Text.Length -le $Limit) { return $Text }
    $prefixLen = $Limit - 15
    if ($prefixLen -lt 1) { $prefixLen = 1 }
    return $Text.Substring(0, $prefixLen) + '... [truncated]'
}

function Write-MarkdownField {
    param(
        [string]$Label,
        [string]$Value
    )
    if ([string]::IsNullOrEmpty($Value)) { $Value = '(not provided)' }
    if ($Value -match "`r?`n") {
        $lines = $Value -split "`r?`n"
        @("**${Label}:**") + ($lines | ForEach-Object { "> $_" })
    }
    else {
        "**${Label}:** $Value"
    }
}

function Get-PlatformName {
    if ($env:OS -eq 'Windows_NT') { return 'windows' }

    $uname = Get-Command uname -ErrorAction SilentlyContinue
    if ($null -ne $uname) {
        $platform = & $uname.Source 2>$null
        if ($platform -eq 'Darwin') { return 'darwin' }
    }

    return 'linux'
}

function ConvertTo-JsonEscape {
    param([string]$Text)
    $Text = $Text -replace '\\', '\\'
    $Text = $Text -replace '"', '\"'
    $Text = $Text -replace "`r", '\r'
    $Text = $Text -replace "`n", '\n'
    $Text = $Text -replace "`t", '\t'
    $Text = $Text -replace [char]8, '\b'
    $Text = $Text -replace [char]12, '\f'
    return $Text
}

function ConvertTo-JsonString {
    param([string]$Key, [string]$Value)
    return "`"$Key`":`"$(ConvertTo-JsonEscape $Value)`""
}

function ConvertTo-JsonNumber {
    param([string]$Key, [int]$Value)
    return "`"$Key`":$Value"
}

function ConvertTo-JsonBool {
    param([string]$Key, [bool]$Value)
    $boolStr = if ($Value) { 'true' } else { 'false' }
    return "`"$Key`":$boolStr"
}

function ConvertTo-JsonTagArray {
    param([string]$CsvTags)
    if ([string]::IsNullOrWhiteSpace($CsvTags)) { return @() }
    return ($CsvTags.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Get-AgentDisplay {
    param(
        [string]$Agent = '',
        [string]$Role = ''
    )

    if (-not [string]::IsNullOrWhiteSpace($Agent) -and -not [string]::IsNullOrWhiteSpace($Role)) {
        return "$Agent ($Role)"
    }
    if (-not [string]::IsNullOrWhiteSpace($Agent)) {
        return $Agent
    }
    if (-not [string]::IsNullOrWhiteSpace($Role)) {
        return "role:$Role"
    }

    return ''
}

function Protect-Text {
    param([string]$Text)
    if ($null -eq $Text) { return '' }
    $Text = $Text -replace '(Bearer\s+)[A-Za-z0-9._-]+', '$1[REDACTED]'
    $Text = $Text -replace '\bgh[pousr]_[A-Za-z0-9]+\b', '[REDACTED_GITHUB_TOKEN]'
    $Text = $Text -replace '\bsk-[A-Za-z0-9_-]+\b', '[REDACTED_API_TOKEN]'
    $Text = $Text -replace '\bAKIA[0-9A-Z]{16}\b', '[REDACTED_AWS_ACCESS_KEY]'
    $Text = $Text -replace '\bxox[baprs]-[A-Za-z0-9-]+\b', '[REDACTED_SLACK_TOKEN]'
    $Text = $Text -replace '(?i)\b(Password|Token|Secret|Api[_-]?Key)(\s*[:=]\s*)[^\s''\"]+', '$1$2[REDACTED]'
    return $Text
}

function Protect-Excerpt {
    param(
        [string]$Text,
        [int]$Limit = 600
    )
    $sanitized = Protect-Text $Text
    return Get-TruncatedText $sanitized $Limit
}

function ConvertTo-NormalizedBool {
    param([string]$Value = 'false')
    switch ($Value.ToLowerInvariant()) {
        { $_ -in '1', 'true', 'yes', 'y', 'on' } { return $true }
        default { return $false }
    }
}

function ConvertTo-SafeInt {
    param([string]$Value = '0')
    if ($Value -match '^-?\d+$') { return [int]$Value }
    return 0
}

function Get-EventFieldValue {
    param(
        $Event,
        [string]$Name,
        $Default = $null
    )

    $prop = $Event.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    return $prop.Value
}

function Get-DerivedCategoryParts {
    param($Event)
    $value = [string](Get-EventFieldValue -Event $Event -Name 'derived_category' -Default '')
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
    param($Value)
    if ($null -eq $Value) { return $null }
    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    if ($text -notmatch '^-?\d+$') { return $null }
    return [int]$text
}

function Test-EventTextMatch {
    param(
        $Event,
        [string]$Query
    )
    if ([string]::IsNullOrWhiteSpace($Query)) { return $true }
    $needle = $Query.ToLowerInvariant()
    foreach ($field in @('title', 'actual_outcome', 'action_taken', 'reading', 'hindsight', 'instruction_text', 'expected_outcome')) {
        $value = [string](Get-EventFieldValue -Event $Event -Name $field -Default '')
        if ($value.ToLowerInvariant().Contains($needle)) {
            return $true
        }
    }
    return $false
}

function Test-EventTimestampFilters {
    param(
        [string]$RecordedAt = '',
        [string]$Date = '',
        [string]$DateFrom = '',
        [string]$DateTo = '',
        [string]$After = ''
    )
    $hasTimestamp = -not [string]::IsNullOrWhiteSpace($RecordedAt)
    $eventDate = ''
    if ($hasTimestamp -and $RecordedAt.Length -ge 10) {
        $eventDate = $RecordedAt.Substring(0, 10)
    }

    if (-not [string]::IsNullOrWhiteSpace($Date)) {
        if ([string]::IsNullOrWhiteSpace($eventDate) -or $eventDate -ne $Date) { return $false }
    }
    if (-not [string]::IsNullOrWhiteSpace($DateFrom)) {
        if ([string]::IsNullOrWhiteSpace($eventDate) -or $eventDate -lt $DateFrom) { return $false }
    }
    if (-not [string]::IsNullOrWhiteSpace($DateTo)) {
        if ([string]::IsNullOrWhiteSpace($eventDate) -or $eventDate -gt $DateTo) { return $false }
    }
    if (-not [string]::IsNullOrWhiteSpace($After)) {
        if (-not $hasTimestamp -or $RecordedAt -le $After) { return $false }
    }
    return $true
}

function ConvertTo-NormalizedRunEffect {
    param([string]$Value)
    switch ($Value) {
        { $_ -in 'blocked', 'degraded', 'noisy', 'continued' } { return $Value }
        'confusing' { return 'continued' }
        'misleading' { return 'degraded' }
        '' { return '' }
        default { throw "Unsupported run effect: $Value" }
    }
}

function ConvertTo-NormalizedGuidanceQuality {
    param([string]$Value)
    switch ($Value) {
        { $_ -in '0', '1', '2', '3', '4' } { return [int]$Value }
        'clear' { return 4 }
        'partial' { return 3 }
        'ambiguous' { return 2 }
        'misleading' { return 1 }
        'not-applicable' { return 0 }
        'confusing' { return 2 }
        '' { return $null }
        default { throw "Unsupported guidance quality: $Value (expected 0-4 or clear/partial/ambiguous/misleading/not-applicable)" }
    }
}

function ConvertTo-NormalizedConfidence {
    param([string]$Value)
    switch ($Value) {
        { $_ -in '1', '2', '3', '4', '5' } { return [int]$Value }
        'low' { return 2 }
        'moderate' { return 3 }
        'medium' { return 3 }
        'high' { return 4 }
        '' { return $null }
        default { throw "Unsupported confidence: $Value (expected 1-5 or low/moderate/high)" }
    }
}

function Test-NarrativeLength {
    param(
        [string]$Label,
        [string]$Value,
        [int]$MinLength
    )
    $length = if ($null -eq $Value) { 0 } else { $Value.Length }
    if ($length -lt $MinLength) {
        throw "$Label must be at least $MinLength characters (got $length). Provide a detailed, substantive account."
    }
}

try {
    $schema = Get-EventSchema
    $sourceTypeEnum = $schema.properties.sources.items.properties.type.enum
    $script:VALID_SOURCE_TYPES = if ($null -ne $sourceTypeEnum -and $sourceTypeEnum.Count -gt 0) { @($sourceTypeEnum) } else { @('file', 'url', 'system-instruction', 'conversation', 'audio', 'visual', 'documentation', 'other') }
} catch {
    $script:VALID_SOURCE_TYPES = @('file', 'url', 'system-instruction', 'conversation', 'audio', 'visual', 'documentation', 'other')
}

function Test-SourceType {
    param([string]$SourceType)
    if ($script:VALID_SOURCE_TYPES -contains $SourceType) { return }
    throw "Unsupported source type: ${SourceType} (expected one of: $($script:VALID_SOURCE_TYPES -join ', '))"
}

function Get-NormalizedFingerprintText {
    param([string]$Text)
    $line = Get-FirstLine $Text
    $line = $line.ToLowerInvariant()
    $line = $line -replace '[^a-z0-9]+', ' '
    return $line.Trim()
}

function Get-EventFingerprint {
    param(
        [string]$Surface,
        [string]$Mode,
        [string]$SourceRef,
        [string]$EventDate,
        [string]$CustomKey = ''
    )
    if (-not [string]::IsNullOrWhiteSpace($CustomKey)) {
        $seed = Get-NormalizedFingerprintText $CustomKey
    }
    else {
        $normalizedSourceRef = Get-NormalizedFingerprintText $SourceRef
        $seed = "$Surface|$Mode|$normalizedSourceRef|$EventDate"
    }
    return Get-ShortSha256 $seed 12
}

function Get-AllTags {
    param([string]$EventsFile)
    if (-not (Test-Path -LiteralPath $EventsFile)) { return '' }
    $tags = [System.Collections.Generic.SortedSet[string]]::new()
    foreach ($line in [System.IO.File]::ReadLines($EventsFile)) {
        $line = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $event = $line | ConvertFrom-Json -ErrorAction Stop
        }
        catch { continue }
        $tagsProp = $event.PSObject.Properties['tags']
        if ($null -ne $tagsProp -and $tagsProp.Value -is [System.Array]) {
            foreach ($t in $tagsProp.Value) {
                if (-not [string]::IsNullOrWhiteSpace([string]$t)) { $tags.Add([string]$t) | Out-Null }
            }
        }
    }
    return ($tags -join ', ')
}

function Get-DefaultOwnerForSurface {
    param([string]$Surface)
    switch ($Surface) {
        'skill' { return 'skill-owner' }
        'instructions' { return 'prompt-owner' }
        'mcp' { return 'mcp-owner' }
        { $_ -in 'tool', 'script' } { return 'tooling-owner' }
        { $_ -in 'code', 'logic' } { return 'implementation-owner' }
        'data' { return 'schema-owner' }
        'environment' { return 'environment-owner' }
        'external-service' { return 'service-owner' }
        'workflow' { return 'workflow-owner' }
        default { return 'triage-owner' }
    }
}

function Get-PriorityScore {
    param(
        [int]$Recurrence = 0,
        [string]$RunEffect = 'continued',
        [int]$GuidanceQuality = 4,
        [int]$MinutesLost = 0,
        [int]$RetriesLost = 0,
        [bool]$WorkaroundUsed = $false
    )
    $score = $Recurrence * 2 + $MinutesLost + $RetriesLost
    switch ($RunEffect) {
        'blocked' { $score += 6 }
        'degraded' { $score += 3 }
        'noisy' { $score += 2 }
        'continued' { $score += 1 }
    }
    # guidance_quality 0-4: lower quality = more priority points
    # 0=N/A(+0), 1=misleading(+3), 2=ambiguous(+2), 3=partial(+1), 4=clear(+0)
    if ($GuidanceQuality -gt 0 -and $GuidanceQuality -lt 4) {
        $score += 4 - $GuidanceQuality
    }
    if ($WorkaroundUsed) { $score += 1 }
    return $score
}

function Get-PriorityBand {
    param([int]$Score)
    if ($Score -ge 16) { return 'high' }
    if ($Score -ge 8) { return 'medium' }
    return 'low'
}

function Resolve-DirectoryPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return (Get-Location).ProviderPath
    }
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if ($null -ne $resolved) {
        $item = Get-Item -LiteralPath $resolved.Path
        if ($item.PSIsContainer) { return $item.FullName }
        return $item.Directory.FullName
    }
    $candidate = [System.IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $candidate -PathType Container) { return $candidate }
    if ([System.IO.Path]::HasExtension($candidate)) {
        return [System.IO.Path]::GetDirectoryName($candidate)
    }
    return $candidate
}

function Get-RepoRoot {
    param([string]$StartPath = (Get-Location).ProviderPath)

    $startDir = Resolve-DirectoryPath $StartPath
    try {
        $git = Get-Command git -ErrorAction Stop
        $repo = & $git.Source -C $startDir rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($repo)) {
            return ($repo | Select-Object -First 1).Trim()
        }
    }
    catch {
    }

    $current = Get-Item -LiteralPath $startDir
    while ($null -ne $current) {
        $gitMarker = Join-Path $current.FullName '.git'
        if (Test-Path -LiteralPath $gitMarker) {
            return $current.FullName
        }
        $current = $current.Parent
    }

    throw "Unable to determine repo root from: $StartPath"
}

function Get-GitSuperprojectRoot {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $result = git rev-parse --show-superproject-working-tree 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) { return $result.Trim() }
    }
    return ''
}

function Get-GitSubmodulePath {
    param(
        [string]$SuperprojectRoot,
        [string]$RepoRoot
    )
    if ($SuperprojectRoot -and $RepoRoot -and $RepoRoot.StartsWith($SuperprojectRoot)) {
        return $RepoRoot.Substring($SuperprojectRoot.Length).TrimStart('/', '\')
    }
    return ''
}

function Get-PreferredLocalDir {
    param([string]$RepoRoot)

    $preferred = @(
        (Join-Path $RepoRoot '.local')
    )
    foreach ($path in $preferred) {
        if (Test-Path -LiteralPath $path -PathType Container) {
            return $path
        }
    }

    $alternate = Get-ChildItem -LiteralPath $RepoRoot -Directory -Filter '.local*' -ErrorAction SilentlyContinue |
        Sort-Object Name |
        Select-Object -ExpandProperty FullName -First 1
    if ($null -ne $alternate) {
        return $alternate
    }

    $localDir = Join-Path $RepoRoot '.local'
    if (-not (Test-Path -LiteralPath $localDir -PathType Container)) {
        New-Item -ItemType Directory -Path $localDir -Force | Out-Null
    }
    return $localDir
}

function Get-TempRoot {
    $path = [System.IO.Path]::GetTempPath()
    if ([string]::IsNullOrWhiteSpace($path)) {
        throw 'Unable to determine system temp path.'
    }
    return $path
}

function Get-DefaultEventsFile {
    param([string]$RepoRoot = '')

    $resolvedRepoRoot = $RepoRoot
    if ([string]::IsNullOrWhiteSpace($resolvedRepoRoot)) {
        try {
            $resolvedRepoRoot = Get-RepoRoot
        }
        catch {
            $resolvedRepoRoot = ''
        }
    }
    else {
        $resolvedRepoRoot = [System.IO.Path]::GetFullPath($resolvedRepoRoot)
    }

    if (-not [string]::IsNullOrWhiteSpace($resolvedRepoRoot)) {
        $localDir = Get-PreferredLocalDir $resolvedRepoRoot
        return [pscustomobject]@{
            RepoRoot = $resolvedRepoRoot
            EventsFile = Join-Path $localDir 'reports/friction/events.jsonl'
        }
    }

    $cwdHash = Get-ShortSha256 ((Get-Location).Path) 12
    $tempRoot = Get-TempRoot
    return [pscustomobject]@{
        RepoRoot = ''
        EventsFile = Join-Path $tempRoot "agent-friction/$cwdHash/events.jsonl"
    }
}

function Resolve-FrictionPaths {
    param(
        [string]$RepoRoot = '',
        [string]$EventsFile = '',
        [string]$IndexFile = ''
    )

    $resolvedRepoRoot = $RepoRoot
    if ([string]::IsNullOrWhiteSpace($EventsFile)) {
        $defaults = Get-DefaultEventsFile $resolvedRepoRoot
        $resolvedRepoRoot = $defaults.RepoRoot
        $resolvedEventsFile = [System.IO.Path]::GetFullPath($defaults.EventsFile)
        $eventsDir = Split-Path -Parent $resolvedEventsFile
        if (-not [string]::IsNullOrWhiteSpace($eventsDir)) {
            New-Item -ItemType Directory -Force -Path $eventsDir | Out-Null
        }
        $resolvedIndexFile = if ([string]::IsNullOrWhiteSpace($IndexFile)) { Join-Path $eventsDir 'INDEX.md' } else { [System.IO.Path]::GetFullPath($IndexFile) }
    }
    else {
        $resolvedEventsFile = [System.IO.Path]::GetFullPath($EventsFile)
        $eventsDir = Split-Path -Parent $resolvedEventsFile
        if (-not [string]::IsNullOrWhiteSpace($eventsDir)) {
            New-Item -ItemType Directory -Force -Path $eventsDir | Out-Null
        }
        if ([string]::IsNullOrWhiteSpace($resolvedRepoRoot)) {
            try {
                $resolvedRepoRoot = Get-RepoRoot $eventsDir
            }
            catch {
                $resolvedRepoRoot = ''
            }
        }
        else {
            $resolvedRepoRoot = [System.IO.Path]::GetFullPath($resolvedRepoRoot)
        }
        $resolvedIndexFile = if ([string]::IsNullOrWhiteSpace($IndexFile)) { Join-Path $eventsDir 'INDEX.md' } else { [System.IO.Path]::GetFullPath($IndexFile) }
    }

    return [pscustomobject]@{
        RepoRoot = $resolvedRepoRoot
        EventsFile = $resolvedEventsFile
        IndexFile = $resolvedIndexFile
    }
}

function Find-FrictionEventsFiles {
    param([string[]]$ScanDirs)

    $discovered = [System.Collections.Generic.List[string]]::new()
    foreach ($dir in $ScanDirs) {
        if ([string]::IsNullOrWhiteSpace($dir)) { continue }
        $resolvedDir = Resolve-DirectoryPath $dir
        if (-not (Test-Path -LiteralPath $resolvedDir -PathType Container)) { continue }
        $found = Get-ChildItem -Path $resolvedDir -Recurse -Filter 'events.jsonl' -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '[/\\]\.local[^/\\]*[/\\]reports[/\\]friction[/\\]events\.jsonl$' } |
            Sort-Object -Property FullName
        foreach ($item in $found) {
            $discovered.Add($item.FullName) | Out-Null
        }
    }
    return $discovered.ToArray()
}

function Test-ActiveProcess {
    param([string]$ProcessId)
    if ([string]::IsNullOrWhiteSpace($ProcessId)) { return $false }
    if ($ProcessId -notmatch '^\d+$') { return $false }
    try {
        Get-Process -Id ([int]$ProcessId) -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Invoke-WithFileLock {
    param(
        [string]$LockRoot,
        [scriptblock]$ScriptBlock
    )

    $lockDir = "${LockRoot}.lock"
    while ($true) {
        try {
            New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop | Out-Null
            [System.IO.File]::WriteAllText((Join-Path $lockDir 'pid'), [string]$PID, [System.Text.UTF8Encoding]::new($false))
            break
        }
        catch [System.IO.IOException] {
            $pidFile = Join-Path $lockDir 'pid'
            $lockPid = $null
            if (Test-Path -LiteralPath $pidFile) {
                try {
                    $lockPid = [System.IO.File]::ReadAllText($pidFile).Trim()
                }
                catch {
                    $lockPid = $null
                }
            }
            if (-not (Test-ActiveProcess $lockPid)) {
                Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
                Remove-Item -Force -Recurse -ErrorAction SilentlyContinue $lockDir
                continue
            }
            Start-Sleep -Milliseconds 200
        }
    }

    try {
        & $ScriptBlock
    }
    finally {
        $pidFile = Join-Path $lockDir 'pid'
        Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
        Remove-Item -Force -Recurse -ErrorAction SilentlyContinue $lockDir
    }
}

function Get-JsonDiagnosticLabel {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -eq '-') { return 'stdin' }
    return $Path
}

function Import-EventJsonObject {
    param(
        [string]$Path,
        [string]$StdinText = ''
    )

    $jsonText = ''
    if ($Path -eq '-') {
        if (-not [string]::IsNullOrEmpty($StdinText)) {
            $jsonText = $StdinText
        }
        else {
            $jsonText = [Console]::In.ReadToEnd()
        }
    }
    else {
        if (-not (Test-Path -LiteralPath $Path)) {
            throw "-FromJson file not found: $Path"
        }
        $jsonText = Get-Content -LiteralPath $Path -Raw
    }

    try {
        $payload = $jsonText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        $detail = $_.Exception.Message.Split([Environment]::NewLine)[0]
        throw "Invalid JSON in -FromJson $(Get-JsonDiagnosticLabel $Path): $detail"
    }

    if ($null -eq $payload) {
        throw "-FromJson $(Get-JsonDiagnosticLabel $Path) must contain a JSON object"
    }
    if ($payload -isnot [pscustomobject] -and $payload -isnot [hashtable]) {
        throw "-FromJson $(Get-JsonDiagnosticLabel $Path) must decode to a JSON object"
    }

    return $payload
}

function Get-JsonFieldValue {
    param(
        [object]$Payload,
        [string]$Key,
        [string]$Current,
        [string]$Default
    )

    if ($Current -ne $Default) {
        return $Current
    }
    $property = $Payload.PSObject.Properties[$Key]
    if ($null -eq $property) {
        return $Current
    }
    $value = $property.Value
    if ($null -eq $value) {
        return $Current
    }
    if ($value -is [bool]) {
        if ($value) { return 'true' }
        return 'false'
    }
    if ($value -is [System.ValueType] -or $value -is [string]) {
        return [string]$value
    }

    $kind = $value.GetType().Name
    throw "-FromJson field '$Key' must be a scalar value, got $kind"
}

function Test-EventFileField {
    param(
        [string]$Path,
        [string]$FieldName,
        [string]$DiagnosticPath
    )

    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if ($null -eq $resolved) {
        return ''
    }
    $fullPath = $resolved.Path
    $repoRoot = ''
    try {
        $repoRoot = Get-RepoRoot $fullPath
    }
    catch {
        return $fullPath
    }

    $canonical = Resolve-FrictionPaths -RepoRoot $repoRoot
    if ($fullPath -ne $canonical.EventsFile) {
        throw "$FieldName from -FromJson $DiagnosticPath must match the selected events file"
    }
    return $fullPath
}

function Import-Events {
    param([string]$EventsFile)

    if (-not (Test-Path -LiteralPath $EventsFile)) {
        return @()
    }

    $events = [System.Collections.Generic.List[object]]::new()
    $lineNumber = 0
    foreach ($line in [System.IO.File]::ReadAllLines($EventsFile, [System.Text.UTF8Encoding]::new($false))) {
        $lineNumber++
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $event = $line | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            $detail = $_.Exception.Message.Split([Environment]::NewLine)[0]
            throw "Invalid JSON in events file at line ${lineNumber}: $detail"
        }
        $events.Add($event)
    }

    return $events.ToArray()
}
