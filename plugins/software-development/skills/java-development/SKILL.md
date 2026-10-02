---
name: java-development
description: >-
  Use for substantive Java source, builds, or tooling. Covers JDK compatibility, APIs, exceptions, resources, concurrency, and ABI; exclude framework-only work.
---

# Java Development

This skill builds on the [Software Development Foundation](../../foundation.md).

Java changes fit what the repository declares in its Maven or Gradle wrapper and build files, toolchains, `module-info.java`, version catalogs, and CI, including the compile JDK, `--release` or source/target level, and runtime JDKs, none of which is inferred from the installed JVM. They follow the repository's packages, nullness annotations, exception policy, and construction patterns, and keep the source, binary, behavioral, and serialization compatibility promises of what the code is: an application, an internal component, or a published library.

- The JDK, language level, build tool, plugins, and dependencies stay as declared unless the task requires a change; generated sources, wrapper files, and dependency locks change only through the tools that own them.
- You SHALL NOT make an irreversible compatibility change that repository evidence cannot settle until the user decides it; without an answer, keep the current contract and mark the path unverified.
- Use only language and library features that every supported compile and runtime target has.
- Public contracts, wire and persistence formats, service registrations, command behavior, and the reflective contracts consumers use stay as they are unless the request changes them.
- Before changing an API, trace its overloads, implementations, callers, reflective use, service loading, and concurrency ownership.
- Keep ownership of resources, tasks, executors, cancellation, and mutable state explicit.
- A new abstraction, dependency, annotation processor, reflection path, or concurrency mechanism is added only for a concrete need.
- Build and test through the repository's wrapper; an IDE result or a run on an unsupported runtime does not show that the change works.

Read each reference that matches the task:

- [Language and API](references/language-and-api.md): Java semantics, collections, generics, null contracts, equality, streams, public API design.
- [Errors and concurrency](references/errors-and-concurrency.md): exceptions, resources, interruption, executors, futures, virtual threads, shared state.
- [Build and compatibility](references/build-and-compatibility.md): JDK and bytecode compatibility, Maven, Gradle, JPMS, dependencies, generation, packaging.
- [Testing and verification](references/testing-and-verification.md): JUnit or TestNG, focused tests, analyzers, integration tests, release verification.
