# WSL And Linux

Excel COM does not run inside native Linux. The supported parity model is:

- Windows PowerShell backend
- POSIX/WSL launcher bridging into Windows PowerShell

The POSIX launcher is its own CLI surface. It must:

- detect WSL or a Windows-accessible shell
- locate `pwsh`, `powershell.exe`, or `powershell`
- own argument validation and `--help`
- translate workbook and manifest paths into Windows paths
- preserve exit codes

When no Windows host bridge is reachable, fail with:

- `error: Excel COM automation is unavailable on this host`
- `hint: run on Windows or inside WSL with Windows PowerShell and desktop Excel installed`
