# Errors, Resources, and Concurrency

Read this reference for exception handling, resource ownership, subprocesses, threads, processes, async code, cancellation, or task lifetimes.

## Keep exception boundaries meaningful

- Catch the narrowest exceptions the boundary can handle.
- Translate exceptions only when the receiving layer needs a stable domain error.
- Let cancellation, termination, and programmer defects propagate unless the boundary has a documented responsibility.
- Use `finally` for unconditional cleanup and `else` when success-only work should remain outside the protected block.
- Avoid silent swallowing and logging the same failure at every layer.

Exception messages are diagnostics, not always stable API. Exception types and timing may be public contracts.

When concurrent work can fail more than once, preserve the repository's aggregation contract rather than silently selecting the first or last failure. Account for the minimum interpreter before using exception-group syntax or APIs.

## Make resource ownership explicit

Do not close resources borrowed from callers.

Generators and lazy iterators defer work and errors until consumed, so moving or replacing one changes when they happen and when its cleanup runs. Ensure partially initialized resources are cleaned up on failure.

Acquisition and release form one protocol. If cleanup is asynchronous or can itself fail or be cancelled, retain its handle, drive it to a terminal state within the owning boundary, and preserve the primary failure according to the public contract. Garbage collection and interpreter shutdown are not deterministic resource owners.

## Fit the concurrency model

Synchronous, threaded, process-based, asynchronous, and framework-scheduled code meet at explicit bridges such as `asyncio.to_thread`, `run_in_executor`, `asyncio.run`, or `run_coroutine_threadsafe`, and one layer owns the executor, event loop, task group, shutdown, and backpressure policy. `asyncio.run` fails inside a running event loop, so a synchronous interface that asynchronous callers may reach overlaps its waits on a thread pool.

For async work:

- The event loop keeps only a weak reference to a task, so a task that no owner holds and awaits can vanish mid-run and lose its exception; a structured scope such as `TaskGroup` owns tasks where the supported interpreter and framework provide it.
- After cancellation is delivered, perform bounded cleanup, settle owned children, and propagate cancellation unless the contract explicitly transforms it. Shielding changes cancellation delivery; it does not transfer ownership or settle the protected task.
- Place concurrency limits, queue capacity, and timeouts at the boundary that owns the constrained resource. Include every buffering stage when deriving the real in-flight bound.
- Preserve context propagation and framework lifecycle hooks.

For threads, processes, interpreters, and executors, account for shared-state synchronization, serialization/start-method constraints, shutdown, exception delivery, and platform differences. Neither incidental bytecode atomicity nor built-in container locking is a synchronization or memory-ordering contract. Avoid wait-for cycles such as work occupying a bounded executor while waiting for work queued to that same executor. Cancelling a future or async waiter may not stop already-running thread or process work; the owner still needs a terminal settlement policy.

Treat queues and worker pools as protocols, not containers. Define capacity, producer completion, consumer termination, failure propagation, task accounting, and the owner of every join. Terminal signaling must remain deliverable under full-capacity and failure conditions; a sentinel per consumer is only one possible design.

## Run subprocesses as typed boundaries

Prefer argument sequences and `shell=False` when invoking a program directly. If shell syntax is genuinely required, make the shell and quoting contract explicit. Define expected exit codes, timeout, working directory, environment inheritance, encoding, and stdout/stderr handling. Captured pipes are bounded queues: drain all owned streams concurrently or use a repository-appropriate communication primitive. On timeout or cancellation, request termination as required, finish draining, reap the process, and then report the terminal outcome. Never treat captured output, a sent signal, or a timeout exception as proof that the process has exited.

When the contract owns a POSIX process group or another descendant boundary, direct-child exit and pipe EOF do not prove that boundary is empty: descendants can close inherited descriptors and keep executing. Retain valid termination authority through the grace interval, apply the declared escalation independently of direct-child communication settlement, and avoid signaling a recycled group identifier after authority is lost.
