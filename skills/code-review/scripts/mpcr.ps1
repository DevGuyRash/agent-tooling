#!/usr/bin/env pwsh
#Requires -Version 5.1
# mpcr.ps1 - Native PowerShell shim for the mpcr Rust binary.
# Mirrors the POSIX `mpcr` wrapper: build-if-needed, pager suppression, exec.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcDir    = Join-Path $ScriptDir 'mpcr-src'
$WindowsNtHost = (($PSVersionTable.PSEdition -eq 'Desktop') -or ($env:OS -eq 'Windows_NT'))
$BinName       = if ($WindowsNtHost) { 'mpcr.exe' } else { 'mpcr' }
$Bin       = Join-Path $SrcDir 'target' 'release' $BinName
$CargoToml = Join-Path $SrcDir 'Cargo.toml'
$CargoLock = Join-Path $SrcDir 'Cargo.lock'

if (-not (Test-Path $CargoLock)) {
    Write-Error "error: missing $CargoLock (skill is expected to be shipped with a lockfile)"
    exit 2
}

# Determine whether a build is needed.
$NeedsBuild = $false
if (-not (Test-Path $Bin)) {
    $NeedsBuild = $true
} else {
    $BinTime = (Get-Item $Bin).LastWriteTimeUtc
    foreach ($f in @($CargoToml, $CargoLock)) {
        if ((Get-Item $f).LastWriteTimeUtc -gt $BinTime) {
            $NeedsBuild = $true
            break
        }
    }
    if (-not $NeedsBuild) {
        foreach ($dir in @('src', 'tests', 'protocols')) {
            $full = Join-Path $SrcDir $dir
            if (Test-Path $full) {
                $newer = Get-ChildItem -Path $full -Recurse -File |
                         Where-Object { $_.LastWriteTimeUtc -gt $BinTime } |
                         Select-Object -First 1
                if ($newer) { $NeedsBuild = $true; break }
            }
        }
    }
}

if ($NeedsBuild) {
    $cargo = Get-Command cargo -ErrorAction SilentlyContinue
    if (-not $cargo) {
        Write-Error "error: mpcr is not built and 'cargo' was not found in PATH`nhint: install a Rust toolchain (rustc + cargo) to build $SrcDir"
        exit 127
    }
    & cargo build --manifest-path $CargoToml --locked --release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Suppress pagers in non-interactive (agent) sessions.
if ([System.Console]::IsOutputRedirected -or -not [Environment]::UserInteractive) {
    $env:PAGER     = 'cat'
    $env:GIT_PAGER = 'cat'
    $env:NO_PAGER  = '1'
}

& $Bin @args
exit $LASTEXITCODE
