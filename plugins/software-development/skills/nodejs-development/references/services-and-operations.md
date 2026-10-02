# Node.js Services and Operations

Load this reference for servers, CLIs, streams, subprocess orchestration, timeouts, signals, shutdown, or operational evidence.

## Servers and Requests

- Set request, header, body, upstream, idle, and shutdown bounds according to the service and framework contract.
- Validate and authorize input before consequential work; parameterization and parsing do not replace authorization.
- Propagate cancellation when a client disconnects or an upstream deadline expires and downstream APIs support it.
- Separate expected client or operational errors from programmer defects and infrastructure failure.
- Avoid returning internal stack traces, secret-bearing causes, or raw dependency errors to callers.
- Respect framework-specific proxy, address, streaming, and error-routing behavior rather than recreating it generically.

## Streams and Backpressure

- Prefer the repository/runtime pipeline abstraction when it correctly joins errors, teardown, and backpressure.
- Do not collect an unbounded stream merely to use a simpler buffer API.
- Account for object mode, encoding boundaries, partial chunks, early consumer exit, and double settlement.
- Pass pipeline cancellation into async generator stages that perform their own waits. When using `finished`, choose its listener-cleanup behavior deliberately; completion observation and listener removal are separate contracts.
- Preserve the selected primary failure or exact abort reason across stream destruction and cleanup. A synthesized wrapper, aggregate, or later teardown error must not silently replace a caller-visible reason when identity is part of the API.
- Verify both producer and consumer cleanup on success, error, timeout, and cancellation.
- Changing a stream's high-water mark rests on workload measurements.

## Lifecycle and Shutdown

- Identify which resources the component owns: listeners, servers, connections, workers, child processes, timers, and temporary files.
- On shutdown, stop accepting work, drain or cancel bounded in-flight work, close owned resources, and set an outcome the supervisor can interpret.
- Make cleanup idempotent so signal, error, and normal completion paths can converge safely.
- Derive HTTP shutdown behavior from the supported Node floor. `server.close()` stops admission and handles idle HTTP connections differently across versions; force-close only after admission closes, and track upgraded sockets or other protocols separately because HTTP close helpers do not own them.
- Respect the deployment platform's termination signal and grace period.
- Do not call `process.exit()` before buffered output and cleanup complete unless immediate termination is the explicit safety behavior.

## Errors and Observability

- Attach context at boundaries while preserving stable error identity or codes used by callers.
- Log once at the layer that owns operational reporting; avoid log-and-rethrow duplication.
- Include request or job correlation through the repository's existing mechanism when concurrency makes attribution difficult.
- Keep secrets, tokens, credentials, and sensitive payloads out of errors, logs, metrics, and traces.
- Treat uncaught exceptions and unhandled rejections as loss of a known-safe state unless the application's supervision contract proves otherwise.

## Verification

- Exercise startup, success, expected failure, cancellation, and bounded shutdown.
- Check exit codes and stdout/stderr contracts for CLIs.
- Check that tests leave no servers, timers, sockets, workers, or subprocesses alive.
- Ensure every new consumer or lifecycle test is selected by the repository's authoritative test command and reaches an explicit terminal assertion or marker; a standalone file that passes only when invoked manually does not protect the default workflow.
- Use representative load and failure injection only when the task owns performance or resilience testing.

Primary authorities: [Node.js streams](https://nodejs.org/api/stream.html) and [Node.js HTTP servers](https://nodejs.org/api/http.html).
