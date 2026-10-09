# C# Exceptions, Async, and Concurrency

## Preserve failure and resource contracts

- Catch only exceptions the boundary can recover from, translate, or report. Broad application boundaries may catch `Exception`; ordinary library flow should not hide unknown failures.
- Preserve stack traces with `throw;` when rethrowing the current exception; `throw ex;` resets the apparent origin.
- Preserve the original exception as `InnerException` when translating and keep stable public exception behavior when callers depend on it.
- Use exception filters when they clarify a recovery condition without mutating state during selection.
- Dispose only resources the component owns. Use `using`/`await using` according to `IDisposable`/`IAsyncDisposable` lifetime and preserve the primary failure if cleanup also fails.
- Do not use finalizers as ordinary deterministic cleanup.

## Keep async APIs truthful

- Return `Task` or `Task<T>` for asynchronous work. Reserve `async void` for event-handler contracts where the caller cannot await.
- Avoid sync-over-async with `.Result`, `.Wait()`, or blocking waits when an async path can propagate; it can deadlock or exhaust threads depending on context.
- A `ValueTask` may be awaited only once, and not concurrently; it fits an API that already returns one or a frequently called path that usually completes synchronously.
- Observe every task's completion or assign it to an explicit supervised lifetime. Discarded tasks lose failures and ownership.
- Preserve the repository's synchronization-context policy and its `ConfigureAwait` usage.
- `Task.Run` moves blocking or CPU work off a UI thread or another thread that must stay responsive; wrapping a synchronous call in it inside a library adds a thread-pool hop without making the call asynchronous.

## Compose task outcomes deliberately

- Choose fail-fast, first-success, partial-result, or collect-all behavior from the public contract. `Task.WhenAll` waits for its inputs but does not cancel siblings.
- When every failure matters, retain the combined task and inspect its aggregate exception and/or each input after all tasks are terminal; an ordinary `await` catch path is not a complete failure ledger.
- Signal sibling cancellation explicitly through an owned or linked `CancellationTokenSource` when policy requires it, then await terminal cleanup and observe late failures.
- Dispose owned token sources, registrations, timers, semaphores, and other coordination resources. Do not dispose caller-owned tokens or sources.

## Propagate cancellation deliberately

- Accept and pass `CancellationToken` where some underlying work observes it.
- Preserve the distinction among caller cancellation, timeout, and operation failure.
- Check cancellation at suitable boundaries and clean up registrations, timers, and partial state.
- Do not catch and convert `OperationCanceledException` into success unless the public contract explicitly defines that outcome.
- Bound retries and ensure side effects are safe before repeating a canceled or failed operation.

## Own subprocesses and redirected I/O

- When stdout and stderr are redirected and either can fill, start both drains before waiting. Close redirected stdin when input is complete so the child can observe EOF.
- Treat wait cancellation, graceful shutdown request, forced termination, descendant policy, process exit, and stream-drain completion as separate events. Canceling `WaitForExitAsync` does not establish that the child stopped.
- Join the process and every owned drain before returning, bound captured output or stream it under an explicit policy, and keep exit, decode, drain, timeout, cancellation, and cleanup failures inspectable.
- Dispose the `Process`, streams, registrations, and timers only after their lifecycle is terminal. Use only process APIs available on every supported target and platform.

## Make streaming pressure and termination explicit

- `IAsyncEnumerable<T>` is pull-driven at its iterator boundary, but a callback, process, or background producer behind it can still be unbounded. Propagate cancellation and ensure early consumer exit reaches enumerator and producer teardown.
- For `Channel<T>`, declare capacity, full mode, ordering, reader/writer multiplicity, loss observation, and the one owner of writer completion and its cause. Waiting and each drop mode are different public behaviors.
- For `System.IO.Pipelines`, keep one owner per reader/writer, pair every read with correct `AdvanceTo`, observe `FlushAsync` completion/cancellation, and complete both ends with the relevant failure. Treat pause/resume thresholds as repository configuration, not universal constants.

## Synchronize shared state

- Establish one coherent policy using `lock`, monitor primitives, semaphores, immutable handoff, atomics, channels, or concurrent collections.
- `volatile` and atomic reads/writes do not make a multi-step invariant atomic.
- Use concurrent collections for documented atomic operations; sequences of operations may still need coordination.
- Keep lock ordering and scope explicit. Avoid awaiting while holding a synchronous lock.
- Account for reentrancy, callbacks, cancellation, and disposal when holding or releasing synchronization primitives.
- Give background workers, channels, timers, and parallel loops bounded lifetime, shutdown, backpressure, and observed failure.

## Reject overbroad rules

- Do not make every method async, every result a `ValueTask`, or every collection concurrent.
- Do not require `ConfigureAwait(false)`, channels, immutable state, reactive streams, or one synchronization primitive everywhere.
- Do not ban all broad catches, locks, blocking calls, or fire-and-forget event handlers without considering the actual boundary.

Primary references: [exception guidance](https://learn.microsoft.com/dotnet/standard/exceptions/best-practices-for-exceptions), [async return types](https://learn.microsoft.com/dotnet/csharp/asynchronous-programming/async-return-types), [`Task.WhenAll`](https://learn.microsoft.com/dotnet/api/system.threading.tasks.task.whenall), [process output](https://learn.microsoft.com/dotnet/api/system.diagnostics.process.standardoutput), [channels](https://learn.microsoft.com/dotnet/core/extensions/channels), [pipelines](https://learn.microsoft.com/dotnet/standard/io/pipelines), [cancellation](https://learn.microsoft.com/dotnet/standard/threading/cancellation-in-managed-threads).
