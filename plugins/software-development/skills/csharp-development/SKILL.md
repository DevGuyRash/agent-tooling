---
name: csharp-development
description: >-
  Use for substantive C# source, projects, or .NET tooling. Covers nullability, disposal, async, APIs, and targets; exclude framework-only ASP.NET/EF and workflow-only work.
---

# C# Development

This skill builds on the [Software Development Foundation](../../foundation.md).

C# changes fit what the repository declares in its `global.json`, solution and project files, `Directory.Build.*`, `Directory.Packages.props`, NuGet configuration, and CI, including the SDK, target frameworks, C# language version, nullable context, implicit usings, and runtime identifiers, none of which is inferred from the installed SDK. They follow the repository's namespace, nullability, exception, disposal, async, dependency, and construction patterns, and keep the source, binary, behavioral, and serialization contracts of what the code is: an application, a tool, an internal assembly, or a published library.

- The SDK, language version, target frameworks, packages, and analyzers stay as declared unless the task requires a change; generated code, lock files, central package files, and API baselines are governed outputs, not casual edit targets.
- You SHALL NOT make an irreversible compatibility change that repository evidence cannot settle until the user decides it; without an answer, keep the current contract and mark the path unverified.
- Use only language features and BCL APIs that every supported target framework and runtime has.
- Public contracts and the serialization, reflection, COM and native, configuration, and generated contracts consumers use stay as they are unless the request changes them.
- Before changing an API, trace its implementations, callers, reflection and dependency-injection use, native and platform use, and async and concurrency ownership.
- Keep ownership of disposable resources, tasks, cancellation, synchronization, and mutable state explicit.
- A new abstraction, package, source generator, result type, mediator, or concurrency mechanism is added only for a concrete need.
- Restore alone, IDE analysis, or a build of one target framework does not show that every supported target builds and passes, or that the configured trimming and AOT checks hold.

Read each reference that matches the task:

- [Language and API](references/language-and-api.md): C# semantics, nullable references, values, records, equality, LINQ, API design.
- [Exceptions, async, and concurrency](references/exceptions-async-and-concurrency.md): exceptions, disposal, tasks, cancellation, synchronization, concurrent state.
- [Projects and compatibility](references/projects-and-compatibility.md): SDK and MSBuild compatibility, projects, target frameworks, NuGet, generation, packaging.
- [Testing and verification](references/testing-and-verification.md): xUnit, NUnit, or MSTest, focused tests, analyzers, API checks, release evidence.
