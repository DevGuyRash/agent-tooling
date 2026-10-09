---
name: async-rust
description: "Use for async Rust: runtimes, task ownership, overlapping awaits, cancellation at suspension points, backpressure, Send and 'static bounds, pinning, and blocking in executors. Composes with rust-development; excludes synchronous-only Rust."
---

# Async Rust

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Asynchronous Rust keeps its lifecycle, cancellation, and resource behavior correct under interleaving. The repository's runtime and version, executor topology, enabled features, test support, and chosen abstractions outrank generic async practice; add a second runtime or swap runtime primitives only when the request changes them.

You SHALL NOT retry a non-idempotent operation until a deduplication or reconciliation contract covers it.

- Know whether each future must be `Send`, may stay local, or crosses task or thread boundaries; keep borrowing futures local where possible, and require `'static` only at boundaries that retain the future.
- Independent futures overlap when they are polled together through a join combinator, a stream, or a task set; consecutive `.await`s run them one after another.
- Bound concurrency where input can outrun downstream work, and size buffers from an explicit throughput and memory contract.
- A future does nothing until polled, while a spawned task runs from the moment it is spawned, so a concurrency limit applies where work is spawned or polled.
- Scoped or supervised task sets own work whose completion or failure a caller observes.
- Retained join handles or cancellation tokens give an owner control of a task's lifecycle.
- A detached task runs independently, reports its own errors, and has a defined shutdown.
- A spawned task's error or panic reaches its owner only through its join handle, so dropping the handle loses it.
- Never hold a synchronous lock guard across `.await` unless that guard and critical section are designed for it.
- At each suspension point where the owner may drop or abort the future, identify the state already mutated, resources held, and externally visible effects; keep multi-step transitions restartable, guarded, or completed by an owner that outlives the waiting future, and skip cancellation machinery where ownership proves the future cannot be abandoned.
- A timeout drops the future it wraps, which stops polling it and leaves spawned tasks, blocking work, and remote effects running.
- Whether filesystem, DNS, compression, foreign calls, CPU-heavy loops, and synchronization block depends on the runtime and platform actually used, since async syntax does not make an operation nonblocking.
- Genuinely blocking or CPU-heavy work goes through the repository's established blocking boundary, keeping that boundary's queue, cancellation, and shutdown contract.
- Futures stay concrete by default, and an async trait, boxed future, manual pin, or stream appears where a present caller needs it.
- Changes to `Send`, `Sync`, cancellation, ordering, buffering, or wake behavior are API changes.
- Tests use deterministic coordination, paused or controlled time where the runtime supports it, and bounded timeouts at the harness edge; they reach cancellation before progress and after partial progress, task failure, shutdown with work in flight, capacity exhaustion, and the required ordering.
- A clean result from a configured concurrency-model tool is evidence, not proof for every schedule.

Read [cancellation and lifecycle](references/cancellation-and-lifecycle.md) for `select`, timeouts, retries, spawned work, streams, bounded queues, or graceful shutdown, and [Send, runtime, and tests](references/send-runtime-and-tests.md) for `Send` or `'static` failures, isolating blocking work, choosing runtime boundaries, or writing async tests.
