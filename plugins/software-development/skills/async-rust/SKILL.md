---
name: async-rust
description: >-
  REQUIRED for Rust async runtime, task-lifecycle, cancellation, backpressure,
  Send-boundary, or pinning work—do not write, review, debug, or scaffold those
  surfaces without this skill. Always compose with rust-development; exclude
  synchronous-only work. If Rust work is asynchronous, use this skill.
---

# Async Rust

This skill builds on the [Software Development Foundation](../../foundation.md).

Asynchronous Rust keeps its lifecycle, cancellation, and resource behavior correct under interleaving. The repository's runtime and version, executor topology, enabled features, test support, and chosen abstractions outrank generic async practice; add a second runtime or swap runtime primitives only when the request changes them, never by preference.

You SHALL NOT retry a non-idempotent operation until a deduplication or reconciliation contract covers it.

- Know whether each future must be `Send`, may stay local, or crosses task or thread boundaries; keep borrowing futures local where possible, and require `'static` only at boundaries that retain the future.
- Know the concurrency and backpressure limits, the timeout, retry, ordering, and partial-progress semantics, and which operations block, are cancellation-safe, or have external effects.
- Every unit of work has an explicit owner and shutdown or cancellation contract: prefer scoped or supervised tasks when a caller must observe completion or failure, retain join handles or cancellation tokens when the lifecycle requires control, and detach work only when its independence, error reporting, and shutdown behavior are deliberate.
- Errors from spawned work are preserved, not logged and forgotten.
- Bound concurrency where input can outrun downstream work, and size buffers from an explicit throughput and memory contract, not an arbitrary large capacity.
- Never hold a synchronous lock guard across `.await` unless that guard and critical section are designed for it.
- At each suspension point where the owner may drop or abort the future, identify the state already mutated, resources held, and externally visible effects; keep multi-step transitions restartable, guarded, or completed by an owner that outlives the waiting future, and skip cancellation machinery where ownership proves the future cannot be abandoned.
- Never assume a timeout stops the underlying operation.
- Whether filesystem, DNS, compression, foreign calls, CPU-heavy loops, and synchronization block depends on the runtime and platform actually used; move genuinely blocking or CPU-heavy work off constrained executors through the repository's established blocking boundary and keep that boundary's queue, cancellation, and shutdown contract, since async syntax does not make an operation nonblocking.
- Async traits, boxed futures, pinning, and streams need a caller that needs the abstraction.
- Changes to `Send`, `Sync`, cancellation, ordering, buffering, or wake behavior are API changes.
- Tests use deterministic coordination, paused or controlled time where the runtime supports it, and bounded timeouts at the harness edge, never sleep-based correctness assertions or unbounded waits; they reach cancellation before progress and after partial progress, task failure, shutdown with work in flight, capacity exhaustion, and the required ordering.
- A clean result from a configured concurrency-model tool is evidence, not proof for every schedule.

Read [cancellation and lifecycle](references/cancellation-and-lifecycle.md) for `select`, timeouts, retries, spawned work, streams, bounded queues, or graceful shutdown, and [Send, runtime, and tests](references/send-runtime-and-tests.md) for `Send` or `'static` failures, isolating blocking work, choosing runtime boundaries, or writing async tests.
