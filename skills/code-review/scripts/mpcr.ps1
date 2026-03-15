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
$BinDir    = Join-Path (Join-Path $SrcDir 'target') 'release'
$Bin       = Join-Path $BinDir $BinName
$BuildStamp = Join-Path $BinDir '.mpcr-build-stamp'
$BuildLock  = Join-Path $BinDir '.mpcr-build.lock'
$BuildLockPidFile = Join-Path $BuildLock 'pid'
$BuildLockStaleAfter = [TimeSpan]::FromSeconds(5)
$BuildLockWaitTimeout = [TimeSpan]::FromMinutes(10)
$CargoToml = Join-Path $SrcDir 'Cargo.toml'
$CargoLock = Join-Path $SrcDir 'Cargo.lock'

if (-not (Test-Path $CargoLock)) {
    Write-Error "error: missing $CargoLock (skill is expected to be shipped with a lockfile)"
    exit 2
}

function Test-MpcrBuildNeedsRefresh {
    if (-not (Test-Path $Bin)) {
        return $true
    }
    if (-not (Test-Path $BuildStamp)) {
        return $true
    }
    $ReferenceTime = (Get-Item $BuildStamp).LastWriteTimeUtc
    foreach ($f in @($CargoToml, $CargoLock)) {
        if ((Get-Item $f).LastWriteTimeUtc -gt $ReferenceTime) {
            return $true
        }
    }
    foreach ($dir in @('src', 'protocols')) {
        $full = Join-Path $SrcDir $dir
        if (Test-Path $full) {
            $newer = Get-ChildItem -Path $full -Recurse -File |
                     Where-Object { $_.LastWriteTimeUtc -gt $ReferenceTime } |
                     Select-Object -First 1
            if ($newer) {
                return $true
            }
        }
    }
    return $false
}

function Get-BuildLockOwnerPid {
    if (-not (Test-Path $BuildLockPidFile)) {
        return $null
    }
    $raw = (Get-Content -Path $BuildLockPidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $raw) {
        return $null
    }
    $digits = ($raw -replace '\D', '')
    if ([string]::IsNullOrWhiteSpace($digits)) {
        return $null
    }
    return [int]$digits
}

function Test-BuildLockOwnerAlive {
    $pid = Get-BuildLockOwnerPid
    if ($null -eq $pid) {
        return $false
    }
    return $null -ne (Get-Process -Id $pid -ErrorAction SilentlyContinue)
}

function Test-BuildLockStale {
    if (-not (Test-Path $BuildLock)) {
        return $false
    }
    $lockInfo = Get-Item $BuildLock -ErrorAction SilentlyContinue
    if ($null -eq $lockInfo) {
        return $false
    }
    $lockAge = [DateTime]::UtcNow - $lockInfo.LastWriteTimeUtc
    if ($lockAge -lt $BuildLockStaleAfter) {
        return $false
    }
    return -not (Test-BuildLockOwnerAlive)
}

function Remove-BuildLock {
    if (Test-Path $BuildLockPidFile) {
        Remove-Item $BuildLockPidFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $BuildLock) {
        Remove-Item $BuildLock -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Determine whether a build is needed.
$NeedsBuild = Test-MpcrBuildNeedsRefresh

if ($NeedsBuild) {
    $cargo = Get-Command cargo -ErrorAction SilentlyContinue
    if (-not $cargo) {
        Write-Error "error: mpcr is not built and 'cargo' was not found in PATH`nhint: install a Rust toolchain (rustc + cargo) to build $SrcDir"
        exit 127
    }
    [System.IO.Directory]::CreateDirectory($BinDir) | Out-Null
    $LockTaken = $false
    $WaitStarted = [DateTime]::UtcNow
    try {
        while (-not $LockTaken) {
            try {
                $null = New-Item -ItemType Directory -Path $BuildLock -ErrorAction Stop
                $LockTaken = $true
                [System.IO.File]::WriteAllText($BuildLockPidFile, "$PID`n")
            } catch {
                if (-not (Test-MpcrBuildNeedsRefresh)) {
                    $NeedsBuild = $false
                    break
                }
                if (Test-BuildLockStale) {
                    Remove-BuildLock
                    continue
                }
                if (([DateTime]::UtcNow - $WaitStarted) -ge $BuildLockWaitTimeout) {
                    Write-Error "error: timed out waiting for $BuildLock; remove the stale lock or retry after the active build completes"
                    exit 124
                }
                Start-Sleep -Milliseconds 100
            }
        }
        if ($NeedsBuild) {
            & cargo build --manifest-path $CargoToml --locked --release --quiet
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            [System.IO.File]::WriteAllText($BuildStamp, '')
            (Get-Item $BuildStamp).LastWriteTimeUtc = [DateTime]::UtcNow
        }
    } finally {
        if ($LockTaken -and (Test-Path $BuildLock)) {
            Remove-BuildLock
        }
    }
}

if (-not (Test-Path $Bin)) {
    Write-Error "error: failed to build $Bin"
    exit 127
}

# Suppress pagers in non-interactive (agent) sessions.
if ([System.Console]::IsOutputRedirected -or -not [Environment]::UserInteractive) {
    $env:PAGER     = 'cat'
    $env:GIT_PAGER = 'cat'
    $env:NO_PAGER  = '1'
}

# Keep agent-facing errors concise by default.
if (-not $env:RUST_BACKTRACE) {
    $env:RUST_BACKTRACE = '0'
}

& $Bin @args
exit $LASTEXITCODE
