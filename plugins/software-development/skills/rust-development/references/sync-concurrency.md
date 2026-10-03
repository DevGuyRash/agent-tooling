# Synchronous Rust Concurrency

Use this reference for `std::thread`, synchronous channels, shared mutable state, worker pools, or atomics. Load `$async-rust` alongside this skill when futures, async tasks, runtimes, or `.await` are part of the contract.

## Define the contract

Preserve required ordering and determinism, and define these contracts before selecting primitives:

- which component owns each worker and each shared resource;
- the unit of work and maximum workers, queued items, and in-flight memory;
- what producers observe at capacity;
- how completion, cancellation, shutdown, worker failure, and panic reach the owner.

## Own every thread

Use scoped threads when workers may borrow scope-owned data and must finish before that scope exits. Scope exit settles unjoined scoped threads, but explicitly join each handle when the owner must observe every return value or panic. Use owned threads when their lifetime crosses the current scope, and retain their `JoinHandle`s under an explicit owner. Do not detach a thread accidentally by dropping its handle.

A safe shutdown stops admission, signals workers, wakes blocked workers, applies the declared drain-or-cancel policy, and joins every owned thread before releasing its dependencies. Join all handles even after one worker fails or panics; early return from the first `join` can detach the rest. An atomic flag alone does not wake a worker blocked on a channel or condition variable; pair shutdown state with a wakeup path.

Distinguish a worker's returned error from a panic reported by `join`. Propagate, aggregate, or deliberately contain both according to the surrounding service contract; do not lose either in logging or cleanup.

## Choose communication deliberately

Prefer message passing when ownership can move with the work and shared state when multiple workers must coordinate one invariant. Use a bounded queue when producers can outrun consumers, and define whether capacity causes waiting, rejection, shedding, coalescing, or durable spill. Do not replace a bounded queue with an unbounded channel merely to avoid handling overload.

Treat channel disconnection as a lifecycle event with defined meaning. A successful send proves channel acceptance, not worker completion; use a result or acknowledgment path when the owner must observe each item's outcome. Ensure every sender clone is eventually dropped; one forgotten sender can keep a receiver blocked during shutdown. `std::sync::mpsc::Receiver` is single-consumer; do not clone it. Choose one dispatcher, per-worker queues, or an intentional mutex-wrapped receiver. That mutex serializes receive/wait: release it before work and verify throughput, fairness, and shutdown.

## Protect shared invariants

Use `Arc` to share ownership, not as evidence that access is synchronized. Put the complete invariant behind the same `Mutex` when partial updates would be invalid. Use `RwLock` only when its read concurrency materially helps and its fairness behavior is acceptable; it is not an automatic upgrade from `Mutex`.

Keep critical sections no broader than the invariant requires, and do not call slow or re-entrant external work while holding a lock unless the contract requires it. Define a consistent lock order when more than one lock may be held to prevent deadlock, or redesign so nested acquisition is unnecessary. Decide how poisoned locks are handled: fail, restore a proven invariant, or propagate the failure. Blindly discarding poison can expose corrupted state.

Wait on a `Condvar` in a predicate loop because wakeups may be spurious or another worker may consume the condition. Change the predicate while holding its mutex, then notify the required waiters; shutdown must make the predicate terminal and wake every waiter that must exit.

## Reserve atomics for atomic contracts

Prefer channels or locks when state spans multiple values or requires compound transitions. Use atomics only when the shared state and its legal transitions can be stated precisely. Choose memory ordering from the required happens-before relationship, not by habit; if that proof is unclear, use a higher-level primitive. Load `$unsafe-rust` too if the implementation requires unsafe blocks, unsafe functions, or unsafe trait implementations.

## Verify lifecycle and interleavings

Make tests coordinate with barriers, channels, condition predicates, or controlled hooks rather than assuming progress after a sleep. Use a bounded outer timeout only to prevent a hung test suite, not as evidence that an ordering occurred.

Exercise capacity behavior, acknowledged work completion, shutdown while idle and busy, blocked-worker wakeup, disconnects, all-consumer failure under producer pressure, worker errors, panics, and required ordering. Assert that every owned handle is settled even when an earlier join fails. Run repository-supported model checking, race analysis, or concurrency sanitizers when already configured and applicable. Report scheduling, platform, or state-space limits that remain unverified.
