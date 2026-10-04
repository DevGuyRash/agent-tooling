---
name: swift-development
description: >-
  Use for Swift source, SwiftPM packages, or tooling: optionals, errors, value and reference semantics, ARC, async/await, actors, Sendable, and API or ABI compatibility. Excludes Apple-UI-only, signing, and Xcode-project work.
---

# Swift Development

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Swift code makes its value, ownership, failure, compatibility, and concurrency contracts explicit. It keeps what the repository's `Package.swift`, resolved dependencies, any Xcode or build configuration, CI, and nearby code establish: Swift tools version, language mode, enabled upcoming features, compiler floor, and concurrency checking mode; products, targets, modules, build system, supported platforms, and availability policy; public API, ABI and library-evolution, serialization, and Objective-C/C interop commitments; and error, optional, ownership, concurrency, and dependency conventions. Swift mode, platform floors, dependencies, concurrency checking, and package resolution change only when the request explicitly changes them.

- Prefer value semantics for independent values and reference identity where shared identity or lifecycle is part of the domain; choose among structs, classes, actors, enums, protocols, generics, and existentials by the semantics required, and keep mutation and visibility as narrow as callers need.
- Optionals express meaningful absence, and `throws` or the repository's result model expresses recoverable failure; handle a failure at the layer that can add actionable context or recover.
- Avoid force unwraps (`!`) and force casts (`as!`) at caller-controlled and environmental boundaries; use them only where a local invariant is reviewable or the repository explicitly treats a violation as programmer error.
- A protocol, type erasure, dependency wrapper, or generic layer needs a real substitution or testing boundary.
- A cross-platform target uses the Foundation framework or Apple-only APIs only where its platform contract provides them.
- Make closure capture and object lifetime explicit where work is retained or escapes, and choose `weak` or `unowned` from actual lifetime guarantees; neither is a universal cycle fix.
- Tasks, continuations, cancellation, actor isolation, and `Sendable` are observable contracts. Cancellation is cooperative: check and propagate it where the operation's contract requires stopping.
- Independent waits overlap as child tasks: `async let` for a fixed few, and a task group for many.
- Computation that warrants parallelism runs as child tasks in a task group, or with `DispatchQueue.concurrentPerform` outside async code, and never blocks the cooperative pool's threads.
- You SHALL NOT silence an isolation diagnostic with `@unchecked Sendable`, a detached task, or an unsafe continuation until a documented invariant justifies it.
- Review a public API change for source compatibility, overload resolution, default arguments, protocol conformances, enum exhaustiveness, availability, symbol exposure, and generated Objective-C names; a change to actor isolation, `async`, `throws`, `Sendable`, ownership, or callback execution context is an API change.
- Implementation-only dependencies and platform types stay out of public signatures unless intentionally exposed.
- Compiler diagnostics and strict-concurrency checking do not replace runtime and integration tests.

Read [ownership and concurrency](references/ownership-and-concurrency.md) for ARC cycles, captures, value and reference semantics, async/await, child tasks and task groups, actors, cancellation, `Sendable`, or isolation diagnostics, and [packages, interop, and compatibility](references/packages-interop-and-compatibility.md) for SwiftPM manifests, module or public API changes, availability, library evolution, Objective-C/C interop, or cross-platform builds.
