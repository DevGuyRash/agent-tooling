@echo off
setlocal
:: mpcr.cmd - Windows shim for the mpcr Rust binary.
:: Tries bash first (Git for Windows / WSL), falls back to PowerShell.

where bash >nul 2>nul
if not errorlevel 1 (
    bash "%~dp0mpcr" %*
    exit /b %ERRORLEVEL%
)

:: bash unavailable; delegate to the native PowerShell shim.
where pwsh >nul 2>nul
if not errorlevel 1 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0mpcr.ps1" %*
    exit /b %ERRORLEVEL%
)

:: Last resort: Windows PowerShell 5.1 (ships with Windows 10+).
where powershell >nul 2>nul
if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mpcr.ps1" %*
    exit /b %ERRORLEVEL%
)

echo error: neither bash nor PowerShell found in PATH. 1>&2
exit /b 127
