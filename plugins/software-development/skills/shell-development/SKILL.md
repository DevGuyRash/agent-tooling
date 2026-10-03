---
name: shell-development
description: >-
  Use for shell scripts, shell modules, or shell-based automation in POSIX sh, Bash, PowerShell, or another shell: quoting, exit status, traps, background jobs, and subprocesses. Excludes incidental one-liners.
---

# Shell Development

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Shell code keeps the interpreter each script actually runs under: the configured runner, CI `shell`, or invoking command outranks the shebang, which outranks the file extension. Quoting, error handling, and syntax differ by dialect, so nothing from one dialect carries into another without checking. For another shell such as zsh or fish, its official documentation and the repository's supported-version tests are the syntax authority; this skill's interface, process, security, and verification rules still apply, it claims no dialect coverage for that shell, and no sibling skill is invented for it.

- A script's arguments, environment inputs, exit status, stdout and stderr, signals and traps, filesystem effects, and subprocess tree, and for sourced libraries and modules its exported functions, names, and module members, are its interface; progress output stays off a stdout that callers parse.
- The interpreter, supported shell versions, and PowerShell editions stay unless the request changes them; never introduce Bash syntax into a POSIX sh script, and surface conflicting interpreter evidence instead of blending dialects.
- Quote for the selected dialect, keep data separate from code, and pass arguments to external commands without reparsing.
- Check a command's status where the code knows which exit codes are acceptable; a later success does not hide an earlier failure.
- Each external command a loop starts per line or item costs a process start, so work over many lines runs as one pipeline stage over the whole stream.
- Independent commands overlap as background jobs whose PIDs are collected with `wait`, or in PowerShell as thread jobs or `ForEach-Object -Parallel`.
- Bound concurrency from one budget and define output order and partial-failure behavior. Work whose result a script reports is settled where it starts: waiting for a command does not wait for jobs it leaves running.
- Temporary files, locks, and processes are released on success, error, interruption, and cancellation.
- Encoding, line endings, and locale stay as consumers depend on them.
- In PowerShell, pipeline objects stay objects, and terminating errors, non-terminating errors, and native exit codes are handled separately.
- One local interpreter does not show portability: parse-check under the supported interpreter, and exercise the supported shells, editions, and platforms when portability-sensitive behavior changes.

Read the reference for each artifact's dialect, [POSIX sh](references/posix-sh.md), [Bash](references/bash.md), or [PowerShell](references/powershell.md); also [concurrency and processes](references/concurrency-and-processes.md) when the work starts background jobs, runs units concurrently, manages timeouts or cancellation, or owns a subprocess tree, and [process security](references/process-security.md) when it handles untrusted values, secrets, privileges, destructive paths, temporary files, or external process construction.
