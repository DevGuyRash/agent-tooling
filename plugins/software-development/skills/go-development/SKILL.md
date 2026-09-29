---
name: go-development
description: >-
  Use for substantive Go source, modules, or tooling. Covers APIs, errors, context, concurrency, resources, and tests; exclude framework-only and workflow-only work.
---

# Go Development

Go changes fit the repository's declared Go and toolchain versions (`go.mod`, any `go.work`, vendoring, build tags, CI), its package boundaries, and the compatibility promises of what it is: an application, a command, an internal package, or a public module. Generated files change through their generator.

- Use syntax and standard-library APIs that every supported Go version has.
- Go, dependencies, `go.mod` directives, and tooling stay as declared unless the task requires a change, and module, workspace, and vendor diffs hold only what the task needs.
- Exported contracts, serialization, and command, environment, filesystem, and network behavior stay as they are unless the request changes them.
- You SHALL NOT make an irreversible compatibility change that repository evidence cannot settle until the user decides it; without an answer, keep the current contract and mark the path unverified.
- Ownership, cancellation, blocking, and error behavior are explicit at the boundary where they matter; before changing an interface, trace its callers, implementations, and tests, and who owns mutable or concurrent state.
- A new dependency, interface, generic abstraction, goroutine, or global is added only for a concrete need.
- A cached test result covers only what its cache key covers; use the repository's convention or `-count=1` when fresh execution matters.

Read each reference that matches the task: [language and API](references/language-and-api.md) for semantics, package and API design, data ownership, interfaces, or generics; [errors and concurrency](references/errors-and-concurrency.md) for errors, context, goroutines, channels, synchronization, or cancellation; [modules and tooling](references/modules-and-tooling.md) for modules, workspaces, dependencies, build constraints, generation, or toolchains; [testing and verification](references/testing-and-verification.md) for tests, fuzzing, race checks, static analysis, or benchmarks.
