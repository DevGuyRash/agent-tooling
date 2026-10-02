# Go Errors and Concurrency

## Keep errors inspectable

- Return errors for failures callers can reasonably handle. Reserve `panic` for unrecoverable initialization, violated internal invariants, or APIs whose established contract requires it.
- Preserve error identity with `%w` when callers should be able to use `errors.Is` or `errors.As`; use `%v` when intentionally hiding the underlying identity.
- Treat exported sentinel errors and concrete error types as API. Changing wrapping, identity, comparability, or fields can break callers.
- Add operation or resource context once, near the boundary where it becomes useful. Avoid repetitive wrappers that obscure the causal chain.
- Do not match error strings when an identity, type, or stable predicate exists.
- Handle an error once: recover, translate, or propagate it. Log-and-return usually duplicates reporting at another layer.
- Keep cleanup reliable with `defer`; preserve the primary failure when cleanup also fails according to the repository's policy.

## Propagate context intentionally

- Accept `context.Context` as the first parameter for request-scoped work; do not pass `nil`.
- Propagate deadlines, cancellation, and request-scoped values rather than replacing a caller's context without reason.
- Call the returned cancel function when creating a derived context, unless ownership is explicitly transferred.
- Do not store contexts in structs or use them as optional-argument bags without a framework-specific contract that justifies it.
- Check cancellation at blocking or long-running boundaries. Preserve meaningful cancellation and deadline errors.

## Own concurrent work

- Give every goroutine an owner, termination condition, and observed outcome. A fire-and-forget goroutine is a resource and error-lifecycle decision.
- A goroutine returns nothing to the code that starts it, so its result, error, or completion reaches an owner only through a channel, a `sync.WaitGroup`, or a group the owner waits on.
- A panic that a goroutine does not recover itself ends the whole program; a `recover` in the goroutine that started it does not catch it.
- Canceling a `context.Context` signals the goroutines that watch it and waits for none of them, so their owner waits for them before closing what they use.
- A goroutine blocked forever on a channel, lock, or call is never collected, and neither is anything it references.
- Establish who closes a channel. Normally the sending owner closes it; receivers must not close a channel merely to stop producers.
- Account for nil channels, closed-channel zero values, buffered capacity, and select fairness when they affect behavior.
- Fan-out stays within its limit through a fixed set of worker goroutines, or a buffered channel used as a semaphore and acquired before each goroutine starts.
- Queues and retries have explicit limits.
- A deliberately synchronous API stays synchronous, with any overlap inside it finished before it returns; Go callers add their own concurrency with goroutines.
- Use `sync.Mutex`, atomics, channels, or immutable handoff according to the state transition; none is universally superior.
- Remember that map access and compound read-modify-write operations require synchronization when shared.
- Keep lock scope and order explicit. Do not call unknown or blocking code while holding a lock unless the contract requires it.
- Goroutine return alone establishes no happens-before relation with another goroutine; use the synchronization event that publishes completion and the state being observed.

## Diagnose concurrent failures

- Reproduce under the repository's supported race detector when available, but do not treat a clean race run as proof of correctness.
- Check goroutine dumps, cancellation paths, channel ownership, queue bounds, and waits before adding sleeps or retries.
- In tests, synchronize on observable events rather than timing guesses.
- Preserve scheduler independence; do not rely on goroutine execution order unless synchronization establishes it.

## Reject overbroad rules

- Do not ban all `panic`, require channels for every coordination problem, or require a goroutine per request.
- Do not add `errgroup`, worker pools, atomics, or context parameters merely to appear idiomatic.

Primary references: [`errors` package](https://pkg.go.dev/errors), [`context` package](https://pkg.go.dev/context), [memory model](https://go.dev/ref/mem), [race detector](https://go.dev/doc/articles/race_detector).
