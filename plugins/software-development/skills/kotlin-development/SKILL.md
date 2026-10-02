---
name: kotlin-development
description: >-
  Use for substantive Kotlin source, builds, or tooling. Covers nullability, JVM interop/ABI, coroutines, and cancellation; exclude Android/framework-only work without Kotlin changes.
---

# Kotlin Development

This skill builds on the [Software Development Foundation](../../foundation.md).

Kotlin changes fit what the repository declares in its Gradle or Maven wrapper, version catalogs, convention plugins, and CI, including the Kotlin, language and API, plugin, JVM toolchain and target, Java, and platform versions, none of which is inferred from local installations. They follow the repository's source-set boundaries, null conventions, coroutine ownership, and Java interop patterns.

- Kotlin, Gradle, plugins, targets, and dependencies stay as declared unless the task requires a change; generated code, wrapper files, lock files, and published API dumps change only through the tools that own them.
- You SHALL NOT make an irreversible compatibility change that repository evidence cannot settle until the user decides it; without an answer, keep the current contract and mark the path unverified.
- Establish whether the code targets JVM, JavaScript, Native, Wasm, or Multiplatform and which source set owns the behavior, and use only language, standard-library, and compiler features that every supported target has.
- Public contracts, serialization, reflection, Java signatures, generated names, and binary behavior that consumers use stay as they are unless the request changes them.
- Before changing an API, find its Java and other platform callers, library consumers, reflection and serialization use, and the owner of the coroutine scopes it touches.
- Keep nullability, mutability, ownership, blocking, cancellation, and dispatch behavior explicit where callers observe them.
- A new abstraction, dependency, coroutine layer, Flow, opt-in API, or compiler plugin is added only for a concrete need.
- Build and test through the repository's wrapper; IDE analysis is not evidence of behavior, and compiling one target or testing on one platform does not show that the others work.

Read each reference that matches the task:

- [Language and API](references/language-and-api.md): Kotlin semantics, types, collections, equality, extension functions, API design.
- [Coroutines and interop](references/coroutines-and-interop.md): null boundaries, coroutines, cancellation, Java and JVM interop, Multiplatform behavior.
- [Build and compatibility](references/build-and-compatibility.md): compiler and target compatibility, Gradle or Maven, source sets, dependencies, generation, packaging.
- [Testing and verification](references/testing-and-verification.md): kotlin.test, JUnit or Kotest, coroutine tests, analyzers, API checks, release evidence.
