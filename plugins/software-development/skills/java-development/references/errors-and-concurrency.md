# Java Errors and Concurrency

## Preserve exception contracts

- Follow the existing API's checked-versus-unchecked policy. Changing a checked exception, runtime type, wrapping layer, or declared signature can break consumers.
- Catch only exceptions the boundary can recover from, translate, or enrich. Ordinary application and library flow does not catch `Throwable` or `Error`: they include VM failures such as `OutOfMemoryError` that the code cannot recover from.
- Preserve the cause when translating with an exception constructor that accepts it.
- Use try-with-resources for owned `AutoCloseable` values when it matches the lifetime. Inspect suppressed exceptions when cleanup competes with a primary failure.
- Do not swallow failures or log-and-rethrow at every layer; choose the boundary that owns reporting.
- Keep messages useful but do not make callers parse them when a type, cause, or stable field can carry the contract.

## Respect interruption and cancellation

- Treat `InterruptedException` as a control signal. Propagate it when the signature permits, or restore the interrupt flag when translating or terminating work.
- If the API separately promises that the caller's interrupt status remains set after propagation, restore it immediately before the exception crosses that boundary; propagation alone normally leaves the flag cleared.
- Do not continue a retry loop after interruption without an explicit contract.
- Give timeouts a unit, monotonic-clock assumption, overflow policy, and cleanup path. Complete fallible duration conversion and deadline construction before acquiring resources, or place acquisition and conversion inside the same cleanup guard. Preserve the distinction among timeout, cancellation, interruption, and operation failure.
- When composing futures, decide which executor runs each stage and how cancellation and exceptional completion propagate.

## Own external processes and redirected I/O

- Start stdout and stderr consumption while the child runs when either redirected pipe can fill; waiting for exit before draining both can deadlock the parent and child.
- Close or finish child stdin when input is complete. Define encoding, output bounds or streaming ownership, and the disposition of partial output.
- Treat process exit and both drainer completions as separate terminal events. Do not return, close their streams, or discard failures until the declared result has observed each owned event.
- Canceling or abandoning an exit-wait future does not establish that the process stopped. Define interruption, timeout, graceful termination, forced termination, and descendant policy, then observe the selected terminal boundary.
- Preserve the exit status and required process, drain, and cleanup failures through the API's result or exception contract. Leave no owned child, drainer, or blocked input writer after completion.

## Apply the Java Memory Model

- Establish a happens-before relationship for shared mutable state using synchronization, locks, volatile publication, atomics, concurrent collections, or task handoff.
- `volatile` supplies visibility and ordering for the variable; it does not make a multi-step state transition atomic.
- Keep invariants protected by one coherent synchronization policy. Mixing locks and unsynchronized access defeats the policy.
- Avoid calling unknown, blocking, or reentrant code while holding a lock unless the contract and ordering are explicit.
- Use concurrent collections for their documented atomic operations, not as proof that multi-operation workflows are atomic.

## Own tasks and executors

- `Executors.newFixedThreadPool` queues submitted tasks without bound, and `newCachedThreadPool` and the virtual-thread-per-task executor start a thread for every task, so none of them limits in-flight work by itself.
- An `ExecutorService` keeps its threads, and non-daemon threads keep the JVM running, until its owner shuts it down and awaits termination; from Java 19, `try`-with-resources on an executor does both.
- Reuse repository-managed executors rather than creating an unbounded pool per call.
- Distinguish CPU-bound work from blocking work when sizing or selecting an executor.
- Computation spread across cores runs on a `ForkJoinPool` or a parallel stream.
- Parallel streams, and `CompletableFuture` async stages given no executor, share the common `ForkJoinPool`, so a blocking stage there stalls every other user of that pool.
- Side effects in a parallel stream stage run in no fixed order.
- A task passed to `submit` keeps its exception inside the returned `Future` until `get` is called, while `execute` hands it to the thread's uncaught-exception handler.
- A `CompletableFuture` holds its failure until a stage handles or joins it, so fire-and-forget is an explicit error and lifecycle policy.
- A synchronous public method that overlaps waits inside keeps its signature by joining the work it started before it returns; returning a `CompletableFuture` instead changes the API for every caller.
- Preserve thread-local, security, logging, and request context only through mechanisms the repository already establishes.

## Compose concurrent outcomes and pressure

- Choose fail-fast, collect-all, first-success, or partial-result semantics explicitly. Cancellation policy and result policy are separate from the mechanism used to wait.
- `CompletableFuture.allOf` establishes completion of its inputs but does not itself provide every outcome. Inspect the component stages when every failure or cancellation must remain observable.
- Canceling a `CompletableFuture` is exceptional completion and does not by itself prove that its computation was interrupted or stopped. Route cancellation through the actual owned work and await admitted tasks when teardown depends on their completion.
- For publishers and other buffered producers, declare capacity, admission behavior, and what full means: wait, reject, drop, or coalesce. Observe loss when it is part of the contract; do not let an apparently asynchronous API hide unbounded memory or an uninterruptible producer wait.
- Give terminal completion one owner, preserve its cause, and ensure subscribers, producers, and owned executors reach their declared terminal state exactly once.
- For callback protocols, publish the required initial state before delivering later signals, keep callbacks outside internal locks, and account for synchronous reentrancy or callback failure without replacing an already-selected terminal cause.

## Treat newer concurrency features as versioned choices

- Virtual threads exist from Java 21 and do not make computation faster or shared state safe.
- Virtual threads are created per task rather than pooled. One blocked inside native code, or inside `synchronized` before Java 24, pins its carrier thread, and per-thread state such as `ThreadLocal` caches and thread-keyed monitoring sees one thread per task.
- Treat structured-concurrency and scoped-value APIs according to their status in the target JDK; preview APIs require explicit build and runtime enablement.

## Reject overbroad rules

- Do not require reactive APIs, `CompletableFuture`, virtual threads, immutable data, or one concurrency library for every task.
- Do not ban synchronized blocks, locks, checked exceptions, or all broad catches; top-level containment boundaries may legitimately differ from library code.

For memory-model and API details, select the specification edition matching the repository's effective target JDK. Primary references: [Java Language Specification index](https://docs.oracle.com/javase/specs/jls/), [Java API specification index](https://docs.oracle.com/en/java/javase/), and [virtual threads (JEP 444)](https://openjdk.org/jeps/444).
