Set-StrictMode -Version Latest

function Get-Slug {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "friction-task" }
    $slug = $Text.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) { return "friction-task" }
    return $slug
}

function Get-ShortSha256 {
    param([string]$Text)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha256.ComputeHash($bytes)
    }
    finally {
        $sha256.Dispose()
    }
    return -join ($hashBytes[0..3] | ForEach-Object { $_.ToString('x2') })
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

function Get-CategoryTags {
    param(
        [string]$Surface,
        [string]$Mode,
        [string]$Impact,
        [string]$TextLower
    )

    $tags = ""
    $tags = Add-CsvItem $tags $Surface
    $tags = Add-CsvItem $tags $Mode
    $tags = Add-CsvItem $tags $Impact

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

    return $tags
}
