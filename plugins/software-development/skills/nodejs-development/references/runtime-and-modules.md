# Node.js Runtime and Modules

Load this reference for Node version compatibility, ESM/CommonJS resolution, paths, files, processes, workers, or environment behavior.

## Runtime Contract

- Reconcile `engines`, version-manager files, CI matrices, containers, deployment configuration, and actual production constraints.
- Use the oldest supported version when evaluating API availability and syntax emitted by a compiler.
- Distinguish Node from browsers, service workers, edge runtimes, Electron, and compatibility layers even when they expose similar APIs.
- Feature detection can complement version policy, but it should not hide an unsupported deployment target.

## ESM and CommonJS

- Resolve semantics from the nearest package scope, filename extension, exports/imports conditions, loader hooks, and consuming toolchain.
- Preserve the difference between static imports, dynamic imports, and `require`, including timing, caching, live bindings, and cycle behavior.
- Use `import.meta.url` and URL conversion for module-relative resources in ESM.
- Keep `__dirname`/`__filename` assumptions confined to CommonJS or explicit compatibility code.
- Treat default-import interop as toolchain-dependent. Test the actual supported consumer rather than relying on editor acceptance.
- Do not expose internal deep paths accidentally when changing an exports map.
- A dual ESM/CommonJS package can create separate caches, instances, class identities, and mutable state. Add dual entry points only with a tested need and prove identity-sensitive behavior when both loaders can coexist.

## Files, Paths, and Data

- Specify encoding when text is required; preserve `Buffer` or typed-array behavior for binary data.
- Use `path` and URL APIs appropriate to the value being handled. Account for Windows drive, UNC, separator, and case behavior when portability is claimed.
- Make overwrite, atomicity, permissions, temporary-file cleanup, and symlink behavior explicit for consequential writes.
- Avoid time-of-check/time-of-use security assumptions around mutable filesystem paths.

## Processes and Workers

- Prefer direct executable plus argument arrays over shell strings. Enable a shell only for syntax that genuinely requires it and constrain inputs.
- Decide how stdin/stdout/stderr are inherited, captured, streamed, and bounded.
- Handle subprocess spawn error, exit, stdio close, signal delivery, cancellation, and cleanup as separate outcomes. Guard error/exit listeners against double settlement and wait for `'close'` when the contract includes terminal stdio.
- Check an already-aborted signal before spawning or acquiring other resources when cancellation promises no side effects. When the API exposes `signal.reason`, preserve the exact reason if identity is contractual, and remove abort listeners at every terminal path.
- Treat `subprocess.killed` as evidence that a signal was sent, not that the process terminated. A shell or parent kill may leave descendants alive; define descendant ownership and verify the complete owned process closure.
- A worker thread or child process owns its message protocol, error and exit handling, and termination; a child process also isolates memory and crashes.
- Avoid sharing mutable process-global configuration across tests or request contexts unless ownership is explicit.

Primary authority: the repository version's documentation from the [Node.js documentation index](https://nodejs.org/docs/) and [child-process API](https://nodejs.org/api/child_process.html). Package and tool behavior may impose narrower contracts.
