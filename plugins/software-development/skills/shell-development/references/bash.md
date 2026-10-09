# Bash

Read this reference only for artifacts explicitly executed by Bash.

## Establish the Bash contract

Inspect the shebang, CI image, deployment hosts, and minimum Bash version. macOS and embedded environments may provide older Bash releases; associative arrays, `mapfile`, namerefs, glob options, and other features have version constraints.

Do not use Bash syntax merely because a `.sh` file happens to work under local Bash. Conversely, do not flatten arrays into POSIX strings when Bash is the declared interface.

## Preserve argument structure

- Use indexed or associative arrays for argument vectors and mappings when supported.
- Expand argument arrays as `"${args[@]}"`; avoid constructing a command string for later evaluation.
- Prefer `[[ ... ]]` for Bash conditional semantics and `(( ... ))` for arithmetic, while preserving intentional glob or regex matching.
- Quote ordinary parameter and command substitutions; make intentional splitting or globbing visually explicit.
- Use parameter-expansion defaults carefully: unset and empty are different states.
- Avoid parsing display output when a stable command or structured interface exists.

In a hand-written option loop, prove that every branch advances or exits. Validate required operands before `shift N`, then test missing, empty, repeated, and `--` boundary cases so malformed input reaches the documented usage status instead of looping or consuming the next option.

`eval`, indirect expansion, namerefs, and dynamically generated code expand authority. Use them only for a real interface that cannot be represented with arrays, functions, or mappings.

## Design failure and pipeline behavior

`set -e`, `ERR` traps, `pipefail`, command substitutions, conditions, and subshells interact in non-obvious ways. Preserve repository policy, but explicitly handle commands whose failure matters.

Capture pipeline status only when the contract requires component-level detail. Avoid depending on parent-shell mutation from a pipeline loop unless the supported Bash behavior is deliberate and tested.

Preserve the original status during traps and cleanup. Define how signals, background jobs, process substitutions, coprocesses, and child processes terminate. Wait for owned jobs and propagate the intended status.

Treat non-interactive job control, process groups, and `wait` options as versioned interfaces rather than folklore. Track the PIDs or jobs this invocation owns; Bash `wait -n` and `wait -p` are useful only when the supported version provides them. A trapped signal can interrupt `wait`, so distinguish interruption from child completion and still settle or terminate the remaining owned work.

## Keep scope and state legible

Use functions and `local` variables where supported by the project's Bash target. Avoid global option changes leaking across sourced files; if a function changes shell options, traps, glob behavior, or current directory, restore or document the caller-visible effect.

Differentiate executing and sourcing. Protect CLI entry logic when a file is also a library, following repository convention.

## Verify

Run the supported Bash parser, commonly `bash -n`, plus repository tests. Run configured ShellCheck, shfmt, Bats, or another tool only through project settings. Exercise supported Bash versions, argument edge cases, pipeline failures, background-job cleanup, sourced behavior, and signals where affected.
