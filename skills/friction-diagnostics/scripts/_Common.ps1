Set-StrictMode -Version Latest

$script:SCHEMA_VERSION = '2.0.0'
$script:TAXONOMY_VERSION = '2.0.0'

function Get-Slug {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "friction-task" }
    $slug = $Text.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) { return "friction-task" }
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
    if ($null -eq $Text) { return "" }
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
    return ($line.Substring(0, $Limit - 3) + "...")
}

function Get-TruncatedText {
    param(
        [string]$Text,
        [int]$Limit = 600
    )
    if ($Text.Length -le $Limit) { return $Text }
    $prefixLen = $Limit - 15
    if ($prefixLen -lt 1) { $prefixLen = 1 }
    return $Text.Substring(0, $prefixLen) + "... [truncated]"
}

function Write-MarkdownField {
    param(
        [string]$Label,
        [string]$Value
    )
    if ([string]::IsNullOrEmpty($Value)) { $Value = "(not provided)" }
    if ($Value -match "`r?`n") {
        $lines = $Value -split "`r?`n"
        @("**$Label:**") + ($lines | ForEach-Object { "> $_" })
    } else {
        "**$Label:** $Value"
    }
}

function Get-PlatformName {
    if ($env:OS -eq 'Windows_NT') { return "windows" }

    $uname = Get-Command uname -ErrorAction SilentlyContinue
    if ($null -ne $uname) {
        $platform = & $uname.Source 2>$null
        if ($platform -eq 'Darwin') { return "darwin" }
    }

    return "linux"
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

function ConvertTo-Base64 {
    param([string]$Text)
    return [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Text))
}

function ConvertFrom-Base64 {
    param([string]$Text)
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Text))
}

function Protect-Text {
    param([string]$Text)
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
    if ($Value -match '^\d+$') { return [int]$Value }
    return 0
}

function ConvertTo-NormalizedStorageMode {
    param([string]$Value)
    switch ($Value) {
        { $_ -in 'handoff', 'artifact', 'telemetry' } { return $Value }
        default { throw "Unsupported storage mode: $Value" }
    }
}

function ConvertTo-NormalizedCaptureMode {
    param([string]$Value)
    switch ($Value) {
        { $_ -in 'explicit', 'threshold', 'synthesis' } { return $Value }
        default { throw "Unsupported capture mode: $Value" }
    }
}

function ConvertTo-NormalizedPrivacyTier {
    param([string]$Value)
    switch ($Value) {
        { $_ -in 'private', 'shared' } { return $Value }
        default { throw "Unsupported privacy tier: $Value" }
    }
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
        { $_ -in 'clear', 'ambiguous', 'misleading', 'not-applicable' } { return $Value }
        'confusing' { return 'ambiguous' }
        '' { return '' }
        default { throw "Unsupported guidance quality: $Value" }
    }
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
        [string]$RootSurface,
        [string]$Mode,
        [string]$InstructionSource,
        [string]$ActualOutcome,
        [string]$ActionTaken,
        [string]$Title,
        [string]$CustomKey = ''
    )
    if (-not [string]::IsNullOrWhiteSpace($CustomKey)) {
        $seed = Get-NormalizedFingerprintText $CustomKey
    } else {
        $sourceKey = Get-NormalizedFingerprintText $InstructionSource
        $outcomeKey = Get-NormalizedFingerprintText $ActualOutcome
        $actionKey = Get-NormalizedFingerprintText $ActionTaken
        $titleKey = Get-NormalizedFingerprintText $Title
        $seed = "$RootSurface|$Mode|$sourceKey|$outcomeKey|$actionKey|$titleKey"
    }
    return Get-ShortSha256 $seed 12
}

function Get-SessionValue {
    param(
        [string]$SessionFile,
        [string]$Key
    )
    if (-not (Test-Path $SessionFile)) { return '' }
    $lines = Get-Content $SessionFile
    $match = $lines | Where-Object { $_ -like "$Key=*" } | Select-Object -First 1
    if ($null -eq $match) { return '' }
    return $match -replace "^$Key=", ''
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
        [string]$GuidanceQuality = 'clear',
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
    switch ($GuidanceQuality) {
        'misleading' { $score += 2 }
        'ambiguous' { $score += 1 }
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

function Get-CategoryTags {
    param(
        [string]$Surface,
        [string]$Mode,
        [string]$RunEffect,
        [string]$GuidanceQuality = 'clear',
        [string]$TextLower
    )

    $tags = ""
    $tags = Add-CsvItem $tags $Surface
    $tags = Add-CsvItem $tags $Mode
    $tags = Add-CsvItem $tags $RunEffect
    if ($GuidanceQuality -ne 'not-applicable') {
        $tags = Add-CsvItem $tags $GuidanceQuality
    }

    if ($TextLower -match 'dispatch') { $tags = Add-CsvItem $tags "dispatch" }
    if ($TextLower -match 'role') { $tags = Add-CsvItem $tags "role" }
    if ($TextLower -match 'slug') { $tags = Add-CsvItem $tags "slug" }
    if ($TextLower -match 'agents\.md') { $tags = Add-CsvItem $tags "agents-md" }
    if ($TextLower -match 'skill\.md') { $tags = Add-CsvItem $tags "skill-md" }
    if ($TextLower -match 'mcp') { $tags = Add-CsvItem $tags "mcp" }
    if ($TextLower -match 'server') { $tags = Add-CsvItem $tags "server" }
    if ($TextLower -match 'cli|command ') { $tags = Add-CsvItem $tags "cli" }
    if ($TextLower -match '\.ps1|powershell') { $tags = Add-CsvItem $tags "powershell" }
    if ($TextLower -match '\.sh|posix') { $tags = Add-CsvItem $tags "posix-sh" }
    if ($TextLower -match 'json') { $tags = Add-CsvItem $tags "json" }
    if ($TextLower -match 'yaml') { $tags = Add-CsvItem $tags "yaml" }
    if ($TextLower -match 'schema') { $tags = Add-CsvItem $tags "schema" }
    if ($TextLower -match 'token|credential') { $tags = Add-CsvItem $tags "token" }
    if ($TextLower -match 'permission') { $tags = Add-CsvItem $tags "permission" }
    if ($TextLower -match 'timeout') { $tags = Add-CsvItem $tags "timeout" }
    if ($TextLower -match 'traceback|stacktrace|stack backtrace') { $tags = Add-CsvItem $tags "stacktrace" }
    if ($TextLower -match 'sandbox') { $tags = Add-CsvItem $tags "sandbox" }
    if ($TextLower -match 'filesystem') { $tags = Add-CsvItem $tags "filesystem" }
    if ($TextLower -match 'path') { $tags = Add-CsvItem $tags "path" }
    if ($TextLower -match 'dependency') { $tags = Add-CsvItem $tags "dependency" }
    if ($TextLower -match 'api|endpoint') { $tags = Add-CsvItem $tags "api" }
    if ($TextLower -match 'rate limit') { $tags = Add-CsvItem $tags "rate-limit" }
    if ($TextLower -match 'context') { $tags = Add-CsvItem $tags "context" }
    if ($TextLower -match 'handoff') { $tags = Add-CsvItem $tags "handoff" }
    if ($TextLower -match 'validation|required') { $tags = Add-CsvItem $tags "validation" }
    if ($TextLower -match 'output') { $tags = Add-CsvItem $tags "output" }
    if ($TextLower -match 'workaround') { $tags = Add-CsvItem $tags "workaround" }

    return $tags
}
