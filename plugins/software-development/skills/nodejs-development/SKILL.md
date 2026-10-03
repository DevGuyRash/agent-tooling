---
name: nodejs-development
description: >-
  Use for Node.js runtime or package code: ESM/CJS resolution, exports, streams, buffers, the event loop, worker threads, child processes, and shutdown. Composes with JavaScript or TypeScript; excludes browser-only work.
---

# Node.js Development

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Node.js code fits the repository's runtime, package, module, resource, and operational contracts and what the code is: a CLI, long-lived service, worker, serverless function, build tool, library, or a mix. Its supported Node range, package manager (with workspaces, lockfile, install mode, registry, and scripts), and module system outrank generic practice; where their sources (`engines`, version files, CI, containers, deployment, the nearest `package.json`, file extensions, `exports` and `imports` maps, compiler output, consumers) disagree, what CI and deployment use wins, and the conflict is surfaced. Generated bundles, declarations, and vendored output change at their source.

- Use only APIs the declared Node range supports unless changing that range is in scope.
- ESM/CommonJS entry points, package conditions, file extensions, and import timing stay unless the task owns a migration.
- Paths, file URLs, the working directory, the executable's location, and the module's location are distinct, and claimed platform portability stays.
- Keep encoding and the binary/text distinction across buffers, streams, files, and the network.
- A synchronous filesystem or process call blocks the event loop, holding every other callback, timer, and request until it returns.
- Asynchronous filesystem, `dns.lookup`, crypto, and zlib calls run on libuv's thread pool, four threads unless `UV_THREADPOOL_SIZE` sets another size, so that pool bounds how many of them progress at once.
- Computation that would hold the event loop runs in `worker_threads`, which also spread it across cores, or in a child process.
- Mutable process-global state is unsafe wherever concurrent tests, workers, requests, or embedding consumers can observe it.
- `readFile`, parsing a whole body, and collecting a stream hold the entire input in memory, while streams and async iteration hold one chunk at a time.
- Honor stream backpressure, preferring established pipeline utilities where they match the repository's error and cleanup contract.
- Propagate cancellation and timeouts across owned operations, and clean up listeners, timers, sockets, files, subprocesses, and streams.
- Cancellation and deadlines reach Node APIs through their `signal` option, including signals from `AbortSignal.timeout()`.
- Handle expected operational failures where the code can recover, translate, retry safely, or terminate deliberately.
- Recovery from an operational failure branches on the Node error's `code`, such as `ENOENT` or `ECONNRESET`, rather than on its message.
- Signals and unobserved failures follow the application's supervision model; nothing continues from unknown state.
- Shutdown stops new work, drains or cancels bounded in-flight work, closes owned resources, and finishes within the platform's grace period.
- An open timer, socket, server, worker, or child process keeps the process alive, so a test run that never exits, or that reports open handles or unobserved rejections, shows a leak.
- Keep the selected package manager and lockfile, generating no competing lockfile; add or upgrade dependencies only within the task, reviewing the effective lockfile and lifecycle-script changes.
- Entry points, `exports`, types, `bin`, `files`, `engines`, dependencies, and workspace links are distribution behavior; when package metadata changes, verify the published shape with the repository's pack or distribution workflow.
- Keep runtime dependencies apart from development tooling, and use peer or optional dependencies only for their actual package semantics.
- Environment, arguments, files, network input, and IPC are untrusted until parsed; no environment variable is assumed present, typed, secret, or reloadable.
- Never pass untrusted input through a shell command string; use argument-vector process APIs with an explicitly selected executable.
- Resolve and authorize filesystem targets before writing, accounting for traversal, symlinks, overwrite behavior, and permissions.
- Keep secrets out of source, command lines, error payloads, logs, and package artifacts.

Read each reference that matches what the work touches:

- [Runtime and modules](references/runtime-and-modules.md): module resolution, filesystem, processes, workers, runtime compatibility.
- [Services and operations](references/services-and-operations.md): servers, CLIs, streams, subprocesses, signals, shutdown, observability.
- [Packages and dependencies](references/packages-and-dependencies.md): manifests, exports, workspaces, installation, dependency review.
