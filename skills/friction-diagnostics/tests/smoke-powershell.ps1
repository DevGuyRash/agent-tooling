Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
. "$root/scripts/_Common.ps1"

$repoDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-smoke-{0}" -f [System.Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $repoDir -Force
& git init -q $repoDir
$null = New-Item -ItemType Directory -Path (Join-Path $repoDir '.local') -Force

$eventsFile = Join-Path $repoDir '.local/reports/friction/events.jsonl'
$indexFile = Join-Path $repoDir '.local/reports/friction/INDEX.md'

function Fail {
    param([string]$Message)
    Write-Error "FAIL: $Message"
    exit 1
}

function Assert-FileExists {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { Fail "missing file: $Path" }
}

function Assert-Contains {
    param([string]$Needle, [string]$Path)
    $content = Get-Content -LiteralPath $Path -Raw
    if (-not $content.Contains($Needle)) { Fail "expected '$Needle' in $Path" }
}

function Assert-NotContains {
    param([string]$Needle, [string]$Path)
    $content = Get-Content -LiteralPath $Path -Raw
    if ($content.Contains($Needle)) { Fail "did NOT expect '$Needle' in $Path" }
}

function Assert-Equals {
    param([string]$Expected, [string]$Actual)
    if ($Expected -ne $Actual) { Fail "expected '$Expected' but got '$Actual'" }
}

try {

# ═══════════════════════════════════════════════════════════════════════
# Test 1: Basic event filing with direct flags
# ══���════════════════════════���═════════════════════════════════��═════════
Write-Host -NoNewline 'Test 1: Basic event filing ... '

$output = & "$root/scripts/report-friction.ps1" `
    -EventsFile $eventsFile `
    -RepoRoot $repoDir `
    -Title "Dispatch role slug mismatch" `
    -SourceType file `
    -SourceRef "SKILL.md" `
    -SourceLine 160 `
    -SourceExcerpt "Use mpcr protocol dispatch --role <ROLE>." `
    -ExpectedOutcome "The CLI would resolve 'architecture' as a valid slug." `
    -ActualOutcome "error: unknown dispatch role: architecture. Bearer ghp_leakedtoken1234567890abcdef12345678." `
    -Reading "The dispatch table had 'Architecture' in the Role column. I plugged in 'architecture'. The CLI rejected it immediately." `
    -Hindsight "I should have run --list-roles first." `
    -Impact blocked `
    -Tags "dispatch,slug-mismatch,mpcr" `
    -Aliases "instructions"

$outputText = ($output | Out-String)
if ($outputText -notmatch 'FRICTION_EVENT_ID=evt-0001') { Fail 'should output event_id' }

Assert-FileExists $eventsFile
Assert-FileExists $indexFile
Assert-Contains '"event_id":"evt-0001"' $eventsFile
Assert-Contains '"impact":"blocked"' $eventsFile
Assert-Contains '"tags":' $eventsFile
Assert-Contains '"aliases":' $eventsFile
Assert-Contains '"sources":[{' $eventsFile
Assert-Contains '"excerpt":"Use mpcr protocol dispatch' $eventsFile
# Token redaction
if ((Get-Content -LiteralPath $eventsFile -Raw).Contains('ghp_leakedtoken')) {
    Fail 'token leaked into events.jsonl'
}
Assert-Contains '[REDACTED]' $eventsFile
# Old schema fields should NOT be present
Assert-NotContains '"schema_version"' $eventsFile
Assert-NotContains '"taxonomy_version"' $eventsFile
Assert-NotContains '"instruction_text"' $eventsFile
Assert-NotContains '"action_taken"' $eventsFile
Assert-NotContains '"derived_category"' $eventsFile
Assert-NotContains '"observed_surface"' $eventsFile
Assert-NotContains '"confidence"' $eventsFile
Assert-NotContains '"guidance_quality"' $eventsFile
Assert-NotContains '"incident_id"' $eventsFile

Write-Host 'OK'

# ════���═════════════════════��════════════════════════════════��═══════════
# Test 2: JSON stdin filing with multiple sources
# ═══════════════════���══════════════════════════════��════════════════════
Write-Host -NoNewline 'Test 2: JSON stdin filing ... '

$jsonPayload = @'
{
  "title": "SSH signing agent unavailable",
  "expected_outcome": "Git would create the commit object.",
  "actual_outcome": "error: 1Password: Could not connect to socket.",
  "reading": "The commit failed during signing because SSH_AUTH_SOCK had no socket available.",
  "hindsight": "I should have checked whether this repo enforces commit signing.",
  "impact": "blocked",
  "tags": ["ssh-auth-sock", "git-signing", "1password"],
  "aliases": ["auth", "git"],
  "sources": [
    {"type": "file", "ref": "functions.exec_command", "excerpt": "git commit -m 'docs: add skill'"},
    {"type": "documentation", "ref": "repo-config", "excerpt": "commit.gpgsign = true"}
  ]
}
'@

$output2 = $jsonPayload | & "$root/scripts/report-friction.ps1" -EventsFile $eventsFile -RepoRoot $repoDir -FromJson -
$output2Text = ($output2 | Out-String)
if ($output2Text -notmatch 'FRICTION_EVENT_ID=evt-0002') { Fail 'should be evt-0002' }

$line2 = (Get-Content -LiteralPath $eventsFile)[1]
if ($line2 -notmatch '"auth"') { Fail 'missing auth alias' }
if ($line2 -notmatch '"git"') { Fail 'missing git alias' }
if ($line2 -notmatch '"ssh-auth-sock"') { Fail 'missing ssh-auth-sock tag' }

Write-Host 'OK'

# ═════��════════════════════════════════════════════════════════════��════
# Test 3: --add-tags on existing event
# ���════════════════════��═════════════════════════════���═══════════════════
Write-Host -NoNewline 'Test 3: --add-tags ... '

& "$root/scripts/report-friction.ps1" -EventsFile $eventsFile -AddTags 'evt-0001' -AddTagsCsv 'cli,testing' | Out-Null
$line1 = (Get-Content -LiteralPath $eventsFile)[0]
if ($line1 -notmatch '"dispatch"') { Fail 'original tags missing after --add-tags' }
if ($line1 -notmatch '"cli"') { Fail "--add-tags didn't add 'cli'" }
if ($line1 -notmatch '"testing"') { Fail "--add-tags didn't add 'testing'" }

Write-Host 'OK'

# ══════════════════════════════════════════════════════��════════════════
# Test 4: --add-aliases on existing event
# ═════════════════════════════════════════��═════════════════════════════
Write-Host -NoNewline 'Test 4: --add-aliases ... '

& "$root/scripts/report-friction.ps1" -EventsFile $eventsFile -AddAliases 'evt-0002' -AddAliasesCsv 'environment' | Out-Null
$line2updated = (Get-Content -LiteralPath $eventsFile)[1]
if ($line2updated -notmatch '"auth"') { Fail 'original aliases missing' }
if ($line2updated -notmatch '"environment"') { Fail "--add-aliases didn't add 'environment'" }

Write-Host 'OK'

# ══════════════���════════════════════════════════════════════════════════
# Test 5: Query by impact
# ═══════════════════════════════════════════════════════════════════════
Write-Host -NoNewline 'Test 5: Query by impact ... '

$queryBlocked = & "$root/scripts/query-friction.ps1" -EventsFile $eventsFile -Impact blocked -Format json
$blockedEvents = $queryBlocked | ConvertFrom-Json
Assert-Equals '2' ([string]$blockedEvents.Count)

Write-Host 'OK'

# ══��══════════════════════════════��═════════════════════════════════════
# Test 6: Query by tag (fuzzy)
# ��══════════════��═══════════════════════════════════════════════════════
Write-Host -NoNewline 'Test 6: Query by tag (fuzzy) ... '

$queryAuth = & "$root/scripts/query-friction.ps1" -EventsFile $eventsFile -Tag 'auth' -Format json
$authEvents = $queryAuth | ConvertFrom-Json
Assert-Equals '1' ([string]$authEvents.Count)

Write-Host 'OK'

# ══════���════════════════════════════════════════════════════════════════
# Test 7: INDEX structure
# ═══════════════════════════════════════════════════════════════════════
Write-Host -NoNewline 'Test 7: INDEX structure ... '

Assert-FileExists $indexFile
Assert-Contains '# Friction Index' $indexFile
Assert-Contains '**Created:**' $indexFile
Assert-Contains '**Last event:**' $indexFile
Assert-Contains '## Events' $indexFile
Assert-Contains '## By Alias' $indexFile
Assert-Contains '## Tags' $indexFile
Assert-Contains 'blocked' $indexFile

Write-Host 'OK'

# ═══════════════════════════════════════════════════════════════════════
# Test 8: Add a continued event
# ═════���═══════════════════════════���═════════════════════════════════════
Write-Host -NoNewline 'Test 8: Mixed impact events ... '

& "$root/scripts/report-friction.ps1" `
    -EventsFile $eventsFile `
    -RepoRoot $repoDir `
    -Title "Repo-wide rustfmt spillover" `
    -SourceType file `
    -SourceRef "chatmux-ui/Cargo.toml" `
    -ExpectedOutcome "Only the touched file would be formatted." `
    -ActualOutcome "rustfmt reformatted many unrelated files." `
    -Reading "I used the crate-level formatter for convenience but it covered many files beyond the bounded fix surface." `
    -Impact continued `
    -Tags "rustfmt,formatting" `
    -Aliases "tool" | Out-Null

$totalEvents = (Get-Content -LiteralPath $eventsFile).Count
Assert-Equals '3' ([string]$totalEvents)

Write-Host 'OK'

# ═══════════════════════════════════════════════════════════════════════
# Cleanup
# ════════���══════════════════════════════════════════════════════════════
Write-Host "`nAll smoke tests passed."

}
finally {
    if (Test-Path -LiteralPath $repoDir) {
        Remove-Item -LiteralPath $repoDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
