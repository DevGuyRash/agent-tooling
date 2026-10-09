# PowerShell

Read this reference only for PowerShell scripts, modules, manifests, functions, or pipeline behavior.

## Establish edition and version

Determine Windows PowerShell versus PowerShell, supported versions, operating systems, remoting hosts, execution policy/signing constraints, and module dependencies. Preserve `.ps1`, `.psm1`, and `.psd1` ownership and exported members.

Do not introduce PowerShell 7-only operators or APIs into Windows PowerShell support, or assume Windows-only commands and path behavior in a cross-platform module.

## Preserve the object pipeline

PowerShell pipelines carry objects until a formatting or text boundary. Return or emit the objects consumers expect; do not replace them with `Format-*`, host-rendered text, or string concatenation inside reusable functions.

- Keep success output distinct from information, verbose, warning, error, debug, and progress streams.
- Avoid incidental success-stream output from helper calls; capture, return, or intentionally discard it.
- Preserve property names, types, ordering expectations, and enumeration behavior used by downstream commands.
- Perform formatting at the outer display boundary, not in reusable data-producing code.

Pipeline input, parameter sets, aliases, validation attributes, and exported function names are public interfaces. Use advanced-function features only when the repository contract benefits from them.

## Handle errors by category

Cmdlets can emit non-terminating errors that `try`/`catch` will not catch unless promoted, commonly with scoped `-ErrorAction Stop`. Scope and restore `$ErrorActionPreference` changes instead of setting it globally.

Native executables have their own exit codes. Check and preserve `$LASTEXITCODE` at the relevant boundary. `$?` and native-error integration vary by PowerShell version and preference settings, including `$PSNativeCommandUseErrorActionPreference`; do not assume cmdlet error semantics apply automatically.

Failure is caller-observable, not merely something printed to the error stream. `Write-Error` inside a nested function, `$PSCmdlet.WriteError()`, and `throw` can affect the caller's `$?` and control flow differently; use the mechanism matching the established function contract and test from the caller. `$LASTEXITCODE` also depends on whether a script is invoked directly, with the call operator, or through `pwsh -File` or `pwsh -Command`, so verify the deployed entry path. Redirection and native-stderr integration changed across PowerShell 7.2 and 7.4; test the supported versions rather than inferring behavior from `$ErrorActionPreference` alone.

Preserve the original error or exit code through `finally` and cleanup. Use `throw` or an error record consistent with the function's established contract.

## Invoke native commands deliberately

PowerShell parses and marshals native arguments differently across versions and platforms. Separate direct invocation with `&`, `Start-Process`, and passage through `cmd.exe` or a batch file: they do not share one argument-vector contract. PowerShell 7.3 changed native argument passing and `$PSNativeCommandArgumentPassing` is platform-sensitive; Windows-mode batch and command-script boundaries retain legacy raw-command behavior. `Start-Process -ArgumentList` joins its values into one command line rather than preserving a universal argv abstraction. For untrusted values, avoid raw batch-command boundaries when possible; for every supported boundary, probe the exact arguments received. Define working directory, environment, encoding, stdout/stderr, timeout, and acceptable exit codes.

Dispose owned .NET resources and stop owned jobs/processes in `finally`. Do not dispose objects supplied by the caller.

## Parallel work and process lifetime

PowerShell jobs, thread jobs/runspaces, remoting jobs, and native processes have different state, output, serialization, cancellation, and cleanup behavior. Process/remoting jobs cross a serialization boundary and can lose live type behavior; thread jobs and runspaces share a process but not ordinary scope and require thread-safe shared state. Treat `$Using:` as capture/access syntax, not synchronization.

Choose the execution domain deliberately and retain the handles needed to wait, receive all streams, stop, and remove only the work this invocation owns. `ForEach-Object -Parallel` is a PowerShell 7 interface; set an explicit `-ThrottleLimit` from the aggregate budget and account for outer jobs or nested parallelism that can multiply it.

For native children, distinguish `Start-Process -Wait` from `Wait-Process`, and test descendant behavior, output redirection, remote-session lifetime, and non-Windows shell lifetime on the supported platforms. Do not promise tree-wide cancellation or detached survival from a parent-process handle alone.

## Verify

Use the repository's supported PowerShell parser/import check, Pester suite, and PSScriptAnalyzer/formatter configuration when present. Test both object values and stream placement, caller-observed `$?`, terminating and non-terminating errors, native nonzero exits, deployed invocation form, module import/export, supported editions, and platform-sensitive paths where affected.
