---
name: concurrency-engineering
description: "Use when code in any language starts, bounds, cancels, or joins concurrent work, new or existing: tasks, threads, goroutines, coroutines, workers, callbacks, subprocesses, queues, locks, and shutdown. Excludes one-at-a-time async calls."
---

# Concurrency Engineering

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Concurrent work is an ownership and lifecycle contract whose admission, progress, failure, cancellation, pressure, and terminal completion are observable. The selected platform's native concurrent form and its synchronization, isolation, memory-visibility, reentrancy, and blocking semantics govern; no one language, runtime, scheduler, or primitive is imposed.

Concurrent code makes explicit which operation owns each task, thread, worker, callback registration, queue, and subprocess; when work is admitted or becomes externally visible, and how much may be in flight or retained; result ordering, partial progress, failure aggregation or cutoff, and retries; what can cancel, what actually stops the work, and which terminal outcome wins; and the terminal boundary after which captured state and dependent resources may be released.

- Detach work only when another explicit supervisor owns its lifetime and outcome.
- Admit work before invoking anything that starts eagerly, and bound queued as well as executing work; a worker limit applied to already-started promises, tasks, or requests does not control admission.
- On cancellation, timeout, shutdown, or failure: stop admission, issue the operation-specific unblock or cancellation, observe every admitted outcome, and join or otherwise terminalize owned execution before releasing state it can reach.
- A cancellation request, caller wakeup, direct-child exit, pipe closure, or dropped task handle is not terminal completion.
- Fix primary and secondary failure precedence instead of letting race timing pick it; keep the exact reason, status, or error identity where the public contract requires it, and retain cleanup failures on an explicit secondary channel.
- Buffering, blocking or backpressure, dropping, coalescing, rejection, or load shedding is chosen from the product contract.
- In-flight work is bounded by the tightest limit it shares, such as a downstream's documented limit, connections, or memory, and by cores for computation; nested pools and fan-out share one budget.
- Prove ordering and bounds directly with barriers, handshakes, controlled executors, virtual time, model checking, race detectors, or platform test facilities; sleeps and one clean stress run are weak evidence.
- Test cancellation before admission, during execution, and during cleanup; early consumer exit; failure while producers or submitters are blocked; duplicate or late callbacks; and that no owned work outlives the terminal state.
- Claims of race freedom, deadlock freedom, fairness, or scalability reach only as far as the evidence and platform guarantees, never to unexercised schedulers, loads, targets, or liveness horizons.

Read [lifecycle and cancellation](references/lifecycle-and-cancellation.md) for task ownership, cancellation, timeouts, cleanup, callbacks, subprocesses, or shutdown; [pressure and coordination](references/pressure-and-coordination.md) for queues, channels, streams, admission, backpressure, shared state, locks, actors, or deadlock; [parallelism and verification](references/parallelism-and-verification.md) for parallel algorithms, worker sizing, fairness, deterministic tests, races, or liveness evidence.
