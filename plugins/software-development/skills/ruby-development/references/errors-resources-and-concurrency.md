# Errors, Resources, and Concurrency

Read this reference for exceptions, cleanup, transactions, threads, processes, Fibers, Ractors, or long-running workers.

## Keep rescue boundaries narrow

Process termination, interrupts, and other conditions outside `StandardError` propagate unless a top-level runtime boundary explicitly owns them.

- Rescue only failures the boundary can recover from, translate, retry, or report once.
- Preserve the original cause when raising a domain exception.
- Use `ensure` for unconditional cleanup and `else` for success-only work when it clarifies scope.
- Do not `return`, `break`, or raise casually from `ensure`: cleanup control flow can replace an in-flight result or exception. When both primary work and cleanup can fail, define which failure remains primary and how the other stays observable.
- Bound retries, including `retry`, by attempt, time, idempotency, and backoff policy.
- Avoid rescuing and silently returning `nil` when callers need to distinguish absence from failure.

Exception class, timing, and sometimes message are observable contracts.

## Make ownership explicit

Do not close caller-owned I/O or commit or roll back a transaction owned by another layer.

Long-running processes amplify leaked connections, subscriptions, threads, and class-level state. Verify both normal and exceptional shutdown paths.

## Fit the concurrency model

Threads, processes, Fibers, schedulers, Ractors, and framework job systems have different sharing and lifecycle rules. Concurrent code uses the project's model, with a named owner for startup, cancellation, backpressure, and shutdown.

- Do not treat an implementation's global lock as a complete synchronization guarantee.
- Protect shared mutable state or isolate it; account for callbacks that can interleave.
- Keep blocking work out of scheduler-sensitive paths unless explicitly delegated.
- Treat queues as protocols: define capacity, producer ownership of closure, drain semantics, one terminal signal per consumer when using sentinels, and what happens when a producer or consumer fails.
- After a first failure, do not let surviving workers start queued operations unless the declared contract intentionally drains by execution. Release blocked producers, discard or account for pending work, and join every worker before exposing the primary failure.
- Request cooperative thread shutdown when possible, then `join` or observe `value`; starting, closing a queue, interrupting, or calling `kill` does not itself prove settlement or propagate a worker failure.
- Propagate worker failures through the framework's expected channel.
- Treat Ractor shareability and framework support as compatibility constraints, not a default architecture.

`Thread#raise` and `Thread#kill` also interrupt code at unsafe points outside scheduler-aware operations, so cancellation is cooperative where the code can make it so. An outer timeout does not show that untrusted work, cleanup, or descendants stopped.

For subprocesses, pass command and arguments through a direct-execution API when possible. Define environment, working directory, timeout, exit status, stdout/stderr, signal, and cleanup behavior rather than relying on success-looking output. With `Open3.popen3`, close stdin when input is complete, drain stdout and stderr concurrently, bound retained output when volume is not trusted, and observe the wait thread. Mark output truncated only after observing bytes beyond the retained limit; exactly-at-limit EOF is not truncation.

On timeout, terminating the direct child is only a request and may not reach descendants; use an owned process group where supported, escalate by policy, and wait/reap before reporting completion. Direct-child exit and pipe EOF do not prove the group is empty because a descendant can close inherited descriptors and continue executing; test and observe the declared descendant boundary explicitly. Keep platform differences explicit.
