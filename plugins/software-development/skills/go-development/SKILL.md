---
name: go-development
description: "Use for Go source, modules, or tooling: APIs, errors, context, goroutines and channels, synchronization, resources, and tests. Excludes framework-only and workflow-only work."
---

# Go Development

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Go code fits the repository's declared Go and toolchain versions (`go.mod`, any `go.work`, vendoring, build tags, CI), its package boundaries, and the compatibility promises of what it is: an application, a command, an internal package, or a public module. Generated files change through their generator.

- Use syntax and standard-library APIs that every supported Go version has.
- Go, dependencies, `go.mod` directives, and tooling stay as declared unless the task requires a change, and module, workspace, and vendor diffs hold only what the task needs.
- Exported contracts, serialization, and command, environment, filesystem, and network behavior stay as they are unless the request changes them.
- You SHALL NOT make an irreversible compatibility change that neither the request nor repository evidence settles; keep the current contract and mark the path unverified.
- Ownership, cancellation, blocking, and error behavior are explicit at the boundaries where callers observe them.
- Trace a changed interface through its callers, implementations, and tests, and through whoever owns the mutable or concurrent state it touches.
- Add a new dependency, interface, generic abstraction, or global only for a concrete need.
- Searching a slice scans every element, while a map lookup hashes the key.
- Map iteration order is unspecified and varies from one loop to the next, so ordered output comes from a slice or from sorted keys.
- Go overlaps waits by running ordinary blocking calls in goroutines.
- Goroutines spread computation across cores up to `GOMAXPROCS`, which divides its running time by at most that count and leaves how that time grows with the input unchanged.
- A cached test result covers only what its cache key covers; use the repository's convention or `-count=1` when tests read uncached state.

Read each reference that matches the task: [language and API](references/language-and-api.md) for semantics, package and API design, data ownership, interfaces, or generics; [errors and concurrency](references/errors-and-concurrency.md) for errors, context, goroutines, channels, synchronization, or cancellation; [modules and tooling](references/modules-and-tooling.md) for modules, workspaces, dependencies, build constraints, generation, or toolchains; [testing and verification](references/testing-and-verification.md) for tests, fuzzing, race checks, static analysis, or benchmarks.
