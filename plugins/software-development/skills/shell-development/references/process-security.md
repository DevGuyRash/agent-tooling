# Process and Security Boundaries

Read this reference in addition to the selected dialect reference when scripts handle untrusted values, secrets, privileges, destructive paths, temporary files, remote input, or external process construction.

## Keep data out of code

- Prefer direct execution with a structured argument vector or collection.
- Do not concatenate untrusted values into shell source, `eval`, `Invoke-Expression`, command strings, trap bodies, or dynamically sourced files.
- When shell parsing is genuinely required, identify the exact parser and quote for that dialect at the final boundary.
- Use `--` where the target command supports it, but do not assume every utility does; validate option-like user values.
- Allowlist command names, subcommands, identifiers, and operation modes when users can influence control structure.

Escaping is parser-specific and not a substitute for authorization.

## Control the execution environment

Resolve trusted executables according to repository policy. Treat `PATH`, working directory, inherited functions/modules, aliases, startup profiles, locale, proxy variables, and environment overrides as inputs. Prefer non-profile execution when automation requires a controlled environment.

Pass only needed environment values to children when practical. Avoid secrets in command arguments, traced output, process listings, logs, error messages, CI annotations, or world-readable files.

## Bound filesystem effects

- Create temporary state without predictable-name races and with suitable permissions.
- Resolve and validate destructive targets before deletion; reject empty, root-like, workspace-wide, or otherwise broader-than-intended paths.
- Account for symlinks, archive traversal, mount points, wildcard expansion, and time-of-check/time-of-use changes.
- Make cleanup idempotent and scoped to resources created by this invocation.
- Do not elevate privilege for work that can remain unprivileged.

## Treat processes as owned resources

Define timeout, cancellation, signals, child-process-tree behavior, stdin, stdout/stderr, and accepted exit codes. Drain or redirect streams so children cannot deadlock. Do not infer success from output alone or lose an early pipeline failure behind a later success.

For retries, require a bounded policy and an idempotent or compensating operation. Preserve partial-failure evidence rather than blindly rerunning destructive work.

## Verify adversarial boundaries

Test empty values, spaces, quotes, wildcard characters, option-like strings, newlines, Unicode/encoding, missing commands, nonzero exits, timeout/interruption, partial files, and cleanup. Add traversal or injection probes when those trust boundaries changed.
