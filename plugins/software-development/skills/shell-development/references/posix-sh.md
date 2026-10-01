# POSIX sh

Read this reference only for artifacts whose execution contract is POSIX `sh` or multiple POSIX-conforming shells.

## Preserve the portability target

`/bin/sh` names a contract, not one fixed implementation. Determine the actual shells and operating systems the repository supports, such as dash, ash, ksh in POSIX mode, or Bash in POSIX mode.

Do not introduce Bash-only arrays, `[[ ... ]]`, `(( ... ))` syntax assumptions, process substitution, brace expansion, `source`, `function`, or `mapfile` into POSIX sh.

Utilities also vary. Check whether the project promises strict POSIX userland or a narrower GNU/BSD/BusyBox environment before selecting flags and output formats.

## Preserve words and records

- Quote parameter and command substitutions unless intentional field splitting or pathname expansion is the contract.
- Use `"$@"` to preserve the caller's argument vector; `"$*"` joins it into one value.
- Use `IFS= read -r` for ordinary line input when backslashes and leading/trailing whitespace must survive.
- Prefer `case` for portable pattern dispatch and complex option branches.
- Keep glob patterns distinct from regular expressions and literal strings.
- Remember command substitution removes trailing newlines and cannot represent arbitrary binary data.

Avoid parsing human-formatted command output when a stable machine-readable interface exists.

## Make status flow explicit

POSIX `set -e` has context-dependent exceptions and is not a substitute for designed error handling. `pipefail` was standardized in POSIX.1-2024, but older POSIX targets and deployed shells may not implement it; use it only when the declared shell matrix supports that contract. Preserve repository policy and explicitly check important commands, especially in conditions, substitutions, pipelines, and cleanup.

Pipeline components commonly execute in subshell environments, so variable changes may not reach the parent. Structure data flow accordingly rather than depending on one shell's extension.

Use traps only for signals and exits the script intentionally owns. Preserve the incoming status before cleanup and avoid masking it with a successful cleanup command.

For background work, record each direct child PID when it is started and wait for every admitted child. Portable `wait` lacks Bash's richer completion-selection interface, and `wait` or `kill` on a child PID reaches only that process, not the processes it started; choose a concurrency and cancellation design the declared shells and operating systems can actually enforce.

## Own temporary state

Create temporary files/directories with the repository's portable secure mechanism, restrictive permissions where needed, and an explicit cleanup owner. Validate paths before recursive deletion. Quote trap-time values safely and avoid constructing trap bodies from untrusted text.

## Verify

Use the supported shell's parse check, commonly `sh -n`, then repository tests. Run configured ShellCheck with the correct dialect if present. For portability-sensitive changes, execute against the declared shell matrix rather than one `/bin/sh` symlink.

Test argument boundaries, empty values, wildcard characters, spaces/newlines, expected failures, pipeline status, interruption, and cleanup where affected.
