---
name: swift-development
description: Use for substantive Swift source, SwiftPM, or tooling. Covers optionals, errors, ownership, concurrency, APIs, and ABI; exclude Apple-UI-only, signing, and Xcode-architecture work.
---

# Swift Development

Swift changes make their value, ownership, failure, compatibility, and concurrency contracts explicit. They keep what the repository's `Package.swift`, resolved dependencies, any Xcode or build configuration, CI, and nearby code establish: Swift tools version, language mode, enabled upcoming features, compiler floor, and concurrency checking mode; products, targets, modules, build system, supported platforms, and availability policy; public API, ABI and library-evolution, serialization, and Objective-C/C interop commitments; and error, optional, ownership, concurrency, and dependency conventions. Swift mode, platform floors, dependencies, concurrency checking, and package resolution change only when the request explicitly changes them.

- Prefer value semantics for independent values and reference identity where shared identity or lifecycle is part of the domain; choose among structs, classes, actors, enums, protocols, generics, and existentials by the semantics required, and keep mutation and visibility as narrow as callers need.
- Optionals express meaningful absence, and `throws` or the repository's result model expresses recoverable failure; handle a failure at the layer that can add actionable context or recover.
- Avoid force unwraps (`!`) and force casts (`as!`) at caller-controlled and environmental boundaries; use them only where a local invariant is reviewable or the repository explicitly treats a violation as programmer error.
- A protocol, type erasure, dependency wrapper, or generic layer needs a real substitution or testing boundary.
- Check a cross-platform target's platform contract before adding Foundation or Apple-only APIs to it.
- Make closure capture and object lifetime explicit where work is retained or escapes, and choose `weak` or `unowned` from actual lifetime guarantees; neither is a universal cycle fix.
- Tasks, continuations, cancellation, actor isolation, and `Sendable` are observable contracts. Cancellation is cooperative: check and propagate it where the operation's contract requires stopping.
- You SHALL NOT silence an isolation diagnostic with `@unchecked Sendable`, a detached task, or an unsafe continuation until a documented invariant justifies it.
- Review a public API change for source compatibility, overload resolution, default arguments, protocol conformances, enum exhaustiveness, availability, symbol exposure, and generated Objective-C names; a change to actor isolation, `async`, `throws`, `Sendable`, ownership, or callback execution context is an API change.
- Implementation-only dependencies and platform types stay out of public signatures unless intentionally exposed.
- Compiler diagnostics and strict-concurrency checking do not replace runtime and integration tests.

Read [ownership and concurrency](references/ownership-and-concurrency.md) for ARC cycles, captures, value and reference semantics, async/await, actors, cancellation, `Sendable`, or isolation diagnostics, and [packages, interop, and compatibility](references/packages-interop-and-compatibility.md) for SwiftPM manifests, module or public API changes, availability, library evolution, Objective-C/C interop, or cross-platform builds.
