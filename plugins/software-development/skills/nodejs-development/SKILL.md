---
name: nodejs-development
description: Use for Node.js runtime or package work involving ESM/CJS resolution, exports, streams, buffers, processes, or resource lifecycles. Compose with JavaScript or TypeScript; exclude browser-only work.
---

# Node.js Development

Node.js changes fit the repository's runtime, package, module, resource, and operational contracts and what the code is: a CLI, long-lived service, worker, serverless function, build tool, library, or a mix. Its supported Node range, package manager (with workspaces, lockfile, install mode, registry, and scripts), and module system outrank generic practice; where their sources (`engines`, version files, CI, containers, deployment, the nearest `package.json`, file extensions, `exports` and `imports` maps, compiler output, consumers) disagree, what CI and deployment use wins, and the conflict is surfaced. Generated bundles, declarations, and vendored output change at their source.

- Use only APIs the declared Node range supports unless changing that range is in scope.
- ESM/CommonJS entry points, package conditions, file extensions, and import timing stay unless the task owns a migration.
- Paths, file URLs, the working directory, the executable's location, and the module's location are distinct, and claimed platform portability stays.
- Keep encoding and the binary/text distinction across buffers, streams, files, and the network.
- Keep synchronous filesystem and process work off latency-sensitive paths; startup, build steps, and small CLIs may use it.
- Mutable process-global state is unsafe wherever concurrent tests, workers, requests, or embedding consumers can observe it.
- Decide buffered versus streamed, sequential versus concurrent, and cancellable or not before choosing an API.
- Honor stream backpressure, preferring established pipeline utilities where they match the repository's error and cleanup contract.
- Propagate cancellation and timeouts across owned operations, and clean up listeners, timers, sockets, files, subprocesses, and streams.
- Handle expected operational failures where the code can recover, translate, retry safely, or terminate deliberately.
- Signals and unobserved failures follow the application's supervision model; nothing continues from unknown state.
- Shutdown stops new work, drains or cancels bounded in-flight work, closes owned resources, and finishes within the platform's grace period.
- Where possible, detect leaked handles, incomplete shutdown, unobserved rejections, and partial cleanup.
- Keep the selected package manager and lockfile, generating no competing lockfile; add or upgrade dependencies only within the task, reviewing the effective lockfile and lifecycle-script changes.
- Entry points, `exports`, types, `bin`, `files`, `engines`, dependencies, and workspace links are distribution behavior; when package metadata changes, verify the published shape with the repository's pack or distribution workflow.
- Keep runtime dependencies apart from development tooling, and use peer or optional dependencies only for their actual package semantics.
- Environment, arguments, files, network input, and IPC are untrusted until parsed; no environment variable is assumed present, typed, secret, or reloadable.
- Never pass untrusted input through a shell command string; use argument-vector process APIs with an explicitly selected executable.
- Resolve and authorize filesystem targets before writing, accounting for traversal, symlinks, overwrite behavior, and permissions.
- Keep secrets out of source, command lines, error payloads, logs, and package artifacts.

Read each reference that matches what the change touches:

- [Runtime and modules](references/runtime-and-modules.md): module resolution, filesystem, processes, workers, runtime compatibility.
- [Services and operations](references/services-and-operations.md): servers, CLIs, streams, subprocesses, signals, shutdown, observability.
- [Packages and dependencies](references/packages-and-dependencies.md): manifests, exports, workspaces, installation, dependency review.
