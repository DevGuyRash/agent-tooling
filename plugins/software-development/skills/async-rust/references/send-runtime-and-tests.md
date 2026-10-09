# Send, Runtime Boundaries, and Tests

Read this reference when a future fails `Send`/`'static` bounds, synchronous work may block the executor, runtime contexts cross, or tests depend on scheduling and time.

## Diagnose bounds from the retention boundary

A spawned future commonly needs `'static` because the executor may retain it beyond the caller's stack frame; this does not mean every async function should own `'static` data. Keep borrowed futures within the scope that proves their lifetime. Move or clone only values the retained task actually owns.

When a future is not `Send`, inspect values live across each `.await`. Common causes include guards, `Rc`, non-thread-safe foreign handles, and trait objects without the required bound. Shorten the live range or use a local executor when locality is the intended contract. Do not add unsafe `Send`/`Sync` implementations to silence the compiler.

## Respect the runtime boundary

Use the repository's established runtime entry points, handles, local-task facilities, and blocking pool. Nested runtime startup can panic, deadlock, or violate resource ownership; do not create a new runtime inside an active async context without an explicit isolation contract.

Classify work by behavior, not API name. An async wrapper around a blocking foreign call still blocks its executor thread. Put blocking or sustained CPU work on the established blocking/compute surface, and bound both queued and active work.

Inspect the selected runtime's cancellation and shutdown contract for blocking tasks. A blocking closure that has started may be non-abortable, may outlive the caller's timeout, and may delay runtime shutdown indefinitely. Give such work cooperative cancellation and a terminal observation path when possible; use a separately owned thread, process, or service for long-lived work whose lifecycle does not fit the runtime blocking pool. Do not report an abort request or shutdown timeout as proof that blocking work stopped.

When terminal observation follows an initiating timeout or cancellation request, do not discard a join, panic, or cleanup failure. Preserve both facts when the error model supports it; otherwise apply the repository's existing error precedence and retain the initiating context.

For manual pin projection, self-referential state, raw callback contexts, unsafe `Send`/`Sync`, and FFI lifetime boundaries, also apply `unsafe-rust`. Async progress and cancellation evidence cannot establish memory safety.

## Test observable schedules

Make tests wait for state transitions through barriers, channels, notifications, or handles. Use the runtime's controlled clock for timers when available; advance only after the relevant task is registered. Put a real-time timeout around the outer test to fail boundedly, not as the assertion that proves ordering.

Test required properties rather than a particular poll sequence. Executors may legally poll, migrate, batch, or wake work differently across versions and targets.

For failures, ensure spawned-task errors reach the test. A parent test that exits while detached work fails is not evidence of success.

## Verification matrix

Cover the runtime features and executor flavor the repository supports. When behavior depends on `Send`, test both retained/spawned and local paths where both are public contracts. Model checking and sanitizers can explore additional schedules, but neither replaces integration behavior on the supported runtime.

Primary anchors: [`Send`](https://doc.rust-lang.org/std/marker/trait.Send.html), [`Sync`](https://doc.rust-lang.org/std/marker/trait.Sync.html), and the selected runtime's official spawning, blocking, shutdown, and test-time documentation.
