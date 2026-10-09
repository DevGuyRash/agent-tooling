# Cancellation and Lifecycle

Read this reference when work can be canceled, timed out, retried, buffered, spawned, or shut down independently of its caller.

## Ownership

For each task, stream, request, or queued item, record:

- who starts it and who observes success or failure;
- who may cancel it and what cancellation means;
- what happens when the owner is dropped;
- whether shutdown drains, aborts, checkpoints, or transfers work;
- which resources and external effects may remain after interruption.

A dropped future stops being polled; it does not automatically undo completed effects or stop work owned elsewhere. Dropping a join handle may detach rather than cancel a task, depending on the runtime and abstraction. An abort or cancellation request may also be nonterminal: await the handle or use the runtime's documented completion witness when shutdown must prove task destructors and owned resources have settled. Use the repository's exact locked primitive contract.

## Review cancellation points

For every branch that can lose a race in `select`-style control flow, identify whether abandoning that future loses buffered data, queue position, fairness, framing progress, capacity, or separately owned work. Consult the selected runtime version's method-level cancellation documentation for every branch; cancellation safety is an operation contract, not a property of `select` syntax, and published safe/unsafe lists may be incomplete. Keep protocol frames, transactions, and state-machine transitions owned by a layer that can resume or reconcile them.

Represent resumable progress with authoritative domain state such as a declared length and consumed offset, not poll count, buffer capacity, allocation shape, or another implementation accident.

When polling order or a biased selection mode is part of progress, state the starvation and shutdown consequence explicitly. Priority is not a substitute for a terminal ownership protocol.

When a timeout wraps an operation, distinguish:

1. the caller stopped waiting;
2. the future was dropped;
3. the underlying OS, service, or task stopped;
4. partial effects were rolled back or reconciled.

Claim each only from its own evidence.

## Retry and shutdown

Retry only errors classified as transient, with an attempt/time budget and an idempotency or deduplication contract. Propagate final failure with attempt context.

For graceful shutdown, stop accepting new work, signal owned tasks, resolve queued work according to policy, await bounded completion, and surface unfinished work. Requesting cancellation is not completion; observe every required terminal task outcome. When the contract defines one shutdown boundary, deliver its stop or abort request to every owned participant before awaiting any one participant; otherwise an early join can let later work cross the boundary without receiving the request. The exact order may differ when a protocol requires it.

## Backpressure

Bound queues and in-flight work from a stated resource or latency budget. Define behavior at capacity: wait, reject, shed, coalesce, or spill through an established durable mechanism. An unbounded channel is appropriate only when the producer itself is strictly bounded and that invariant is reviewable.

## Verification

Use barriers, channels, test clocks, and explicit task handles instead of timing guesses. Test cancellation at multiple progress points, retry exhaustion, full capacity, receiver/owner drop, and shutdown with in-flight failure.

Primary anchors: [`Future`](https://doc.rust-lang.org/std/future/trait.Future.html), [Async Book](https://rust-lang.github.io/async-book/), and the selected runtime's own cancellation, selection, task, and join documentation.
