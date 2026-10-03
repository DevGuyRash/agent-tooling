# Kotlin Coroutines and Interop

## Harden platform null boundaries

- Treat Java platform types as unchecked evidence, not as non-null guarantees. Validate or adapt them at the narrowest boundary with domain context.
- Preserve and interpret Java nullness annotations according to the repository's compiler settings and annotation ecosystem.
- Do not spread defensive `!!` or nullable types through Kotlin solely because one Java boundary is uncertain.
- Check generic arguments, arrays, SAM conversions, raw types, and mutability when Java types cross the boundary.

## Own coroutine lifecycles

- Launch work in a scope whose owner, parent job, cancellation, and failure policy match the component lifecycle.
- When the project and every affected target provide a compatible coroutine facility, keep child work within an owned scope. Where coroutines are not part of the repository contract, independent waits overlap through the task abstraction it already uses.
- Choose fail-together, supervised, first-success, or collect-all behavior deliberately. `coroutineScope` and `supervisorScope` have different sibling-failure policies; neither turns unobserved child outcomes into an aggregate result.
- Observe every started task. `launch`, `async`, `join`, `await`, `awaitAll`, and `CoroutineExceptionHandler` expose different failure paths; a handler does not recover ordinary child failure or consume an `async` result.
- Use a detached or global scope only when process-lifetime ownership, terminal failure reporting, and shutdown are explicit and independently supervised.
- Propagate suspending APIs rather than inserting `runBlocking` inside suspend-capable code. Use blocking bridges only at genuine synchronous entrypoints.
- Select a dispatcher for the operation and repository architecture; do not hardcode one when the caller or framework owns execution context.
- Keep blocking calls off a constrained coroutine dispatcher through the repository's established boundary.
- Bound admitted or in-flight operations at the resource boundary. Dispatcher parallelism limits executing work, not necessarily the number of suspended requests, retained inputs, open handles, or queued coroutines.

## Preserve cancellation

- Cancellation is cooperative and commonly represented by `CancellationException`. Do not swallow it in broad exception handling.
- A canceled wait does not necessarily interrupt a blocking Java call or close its resource. If the public contract promises prompt termination, route cancellation to the actual operation through its supported interrupt, close, or cancellation mechanism and await the owned terminal boundary.
- For a blocking operation that requires `close` or another action to unblock, initiate that action at cancellation onset before joining the blocking worker. Closing only after `await` or `join` returns creates a cycle when return itself depends on close; `runInterruptible` helps only when the operation actually responds to interruption.
- Put cleanup in `finally`; use `NonCancellable` only for the smallest suspending cleanup that must complete, and preserve the initiating cancellation or failure when cleanup also fails.
- Bound retries, polling, buffers, fan-out, and flow collection. Check cancellation in CPU-heavy loops.
- Distinguish timeout, cancellation, upstream failure, and empty completion in public behavior.
- Do not use delays as synchronization in tests or production coordination.

## Own streams and callback bridges

- Identify whether a stream is cold, hot, shared, replaying, pull-driven, or backed by an independent producer; bind producer lifetime to the declared owner.
- Declare capacity and full-buffer behavior where a producer can outrun consumers: suspend, reject, drop oldest, drop latest, or conflate. Observe loss when the contract makes it significant; do not inherit library defaults as domain policy.
- Preserve Flow context and exception transparency. Use the selected operators for context changes and upstream recovery rather than emitting after a failed emission or leaking producer context downstream.
- For `callbackFlow` or equivalent adapters, register and unregister exactly once through the owned close path, handle cancellation racing registration and late callbacks, and do not emit after terminal closure.
- Give terminal completion or failure one owner, preserve its cause when unregistration also fails, and wait for required producer/resource cleanup before declaring the stream complete.

## Maintain Java/JVM compatibility

- A top-level function compiles into a facade class named after its file, so moving it to another file changes the class Java callers name unless `@file:JvmName` keeps that name.
- Inspect emitted JVM signatures when changing default arguments, properties, companion members, inline/value classes, wildcards, overloads, or suspend functions.
- Preserve old declarations or explicit compatibility bridges when evolving published parameter lists. A new default parameter, generated overload, or source-compatible call does not by itself prove that old Kotlin bytecode, default-argument stubs, named calls, or Java descriptors still link.
- Treat `jvm-default` mode and public inline bodies as compatibility inputs. Do not change bridge generation or inline implementation assumptions without old-consumer evidence.
- Add `@JvmOverloads`, `@JvmStatic`, `@JvmName`, wildcard annotations, or `@Throws` only for a demonstrated Java-call-site contract.
- Remember that Kotlin does not enforce Java checked exceptions; Java consumers may still require declared exception metadata.
- Preserve Java bean/property expectations, null annotations, visibility, and overload resolution where callers depend on them.
- Treat inline public function bodies as compatibility surface because consumer bytecode may contain them.

## Keep Multiplatform boundaries honest

- Put portable behavior in the appropriate common source set and platform behavior in target source sets.
- Do not call JVM APIs from common code or assume all targets share threading, reflection, filesystem, exception, or test behavior.
- Use `expect`/`actual` only for a real platform boundary and preserve target completeness.
- Verify every affected target available in the repository, not only JVM compilation.

## Reject overbroad rules

- Do not require Flow, `suspend` on every function, or one dispatcher for all work, and do not ban `GlobalScope` where process-lifetime ownership is explicit.
- Do not blanket-add Java interop annotations or generate overloads that expand a public API without need.
- Do not treat Android lifecycle rules as core coroutine or Kotlin rules; route them to the Android skill.

Primary references: [coroutine basics](https://kotlinlang.org/docs/coroutines-basics.html), [cancellation](https://kotlinlang.org/docs/cancellation-and-timeouts.html), [Java interop](https://kotlinlang.org/docs/java-interop.html), [Multiplatform source sets](https://kotlinlang.org/docs/multiplatform-discover-project.html).
