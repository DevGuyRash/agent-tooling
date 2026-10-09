# JavaScript Async, Errors, and APIs

Load this reference for promises, events, cancellation, concurrency, resource lifetime, or public failure behavior.

## Promises and Concurrency

- Return or await promises along every relevant path. If work is intentionally detached, attach rejection handling and expose failure through the repository's logging or supervision mechanism.
- Promise executors run during construction, and calling an async operation usually starts it before its promise is handed elsewhere. Admit inputs before invoking the operation; mapping every input to a promise and only then applying a limiter cannot bound already-started work.
- Use sequential awaiting when order, dependency, resource bounds, or failure cutoff requires it.
- Use concurrent aggregation only for independent work. Choose fail-fast, all-outcome, first-success, or first-settlement behavior from the contract; promise combinators observe their inputs but do not cancel sibling work.
- When an aggregate can settle before every side effect is terminal, cancel through an API the work actually observes, then await or otherwise observe every admitted operation before releasing shared resources or returning a terminal ownership claim. A timeout implemented with `Promise.race` does not stop its loser.
- Avoid `async` promise constructors and unnecessary promise wrapping; connect completion and failure directly.
- Preserve the difference between synchronous throws and asynchronous rejection when callers can observe it.

## Cancellation and Cleanup

- Propagate an existing `AbortSignal` rather than inventing an incompatible cancellation channel.
- Treat abort as a request, not proof that work stopped. Check an already-aborted signal before registering, observe it at meaningful admission and execution boundaries, preserve its reason when the public contract supports that, and remove abort listeners after settlement.
- Clean up timers, subscriptions, event listeners, streams, locks, and acquired resources through the API's supported lifecycle.
- Make timeout behavior distinguishable from cancellation and underlying failure when recovery differs.
- Avoid races between completion, cancellation, and cleanup by making one path own settlement while every path reaches the same terminal cleanup boundary.

## Errors

- Throw `Error` instances or repository-defined error types, not bare strings.
- Preserve the original error as `cause` when adding actionable context and the supported runtime allows it.
- Do not catch merely to log and rethrow if that duplicates reporting or leaks sensitive data.
- Catch at a boundary that can recover, translate, add context, or guarantee cleanup.
- Use stable error classes or codes for machine decisions when the existing API supports them; do not make new callers parse prose.

## API Contracts

- Define whether callbacks can run synchronously, once, repeatedly, or after disposal.
- For async iterables and callback-to-iterator adapters, define buffering or pull pressure, propagate cancellation, and ensure early loop exit reaches iterator and producer teardown; yielding values does not by itself bound an independent producer.
- Keep event names, payload shapes, return values, error modes, and ordering stable unless the task changes the contract.
- Validate untrusted data at the boundary where assumptions become program invariants.
- Avoid boolean-heavy signatures when callers cannot tell what each flag means; follow established API style before introducing an options object.
- Document only constraints that callers cannot infer from types, names, and ordinary behavior.

For host-specific event-loop, stream, process, or filesystem behavior, compose with the appropriate runtime skill.

Primary references: [ECMAScript Promise objects](https://tc39.es/ecma262/multipage/control-abstraction-objects.html#sec-promise-objects), [DOM aborting ongoing activities](https://dom.spec.whatwg.org/#aborting-ongoing-activities), [HTML event loops](https://html.spec.whatwg.org/multipage/webappapis.html#event-loops).
