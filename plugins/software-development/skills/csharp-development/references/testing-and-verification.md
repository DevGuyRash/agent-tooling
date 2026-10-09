# C# Testing and Verification

## Adapt to the existing suite

- Preserve xUnit, NUnit, MSTest, Expecto, or repository-specific frameworks and runners rather than migrating for preference.
- Reuse fixtures, assertions, data cases, mocking tools, snapshots, and test project conventions already present.
- Test observable contracts. Avoid asserting private implementation, incidental LINQ types, scheduler order, or exact exception text unless contractual.
- Keep unit, integration, functional, architecture, and end-to-end tests in their configured projects and commands.
- Make concurrent and async tests await observable completion rather than sleep or block on tasks.

## Use a risk-shaped ladder

1. Restore only when needed under repository policy and compile the affected project/target.
2. Run the focused test through the repository's supported filter or test command.
3. Run affected test projects, target frameworks, and integration tasks.
4. Run configured formatting, compiler warnings, analyzers, source-generator, coverage, API, trimming, or AOT checks.
5. Pack or publish to a safe local destination and inspect artifacts when packaging or public APIs change.
6. Exercise the supported SDK/runtime/platform matrix for changes that use or alter an API, language feature, dependency, or build setting whose availability differs across it.

Repository configuration determines the authoritative surface.

## Check specialized boundaries

- For nullable changes, compile with the repository warning policy and test oblivious/runtime null inputs where relevant.
- For async changes, test success, multiple simultaneous failures, cancellation, timeout, cleanup failure, and terminal ownership without sync-over-async; inspect every task outcome when the contract is collect-all.
- For process changes, use helpers that can fill stdout and stderr, wait for stdin EOF, exit nonzero, hang, and outlive a parent; assert process and drain completion, bounded output, failure precedence, and no surviving owned work.
- For channels and async streams, use a deliberately slow or early-exiting consumer; assert the declared bound/full mode, ordering or loss, completion cause, producer teardown, enumerator disposal, and late-write behavior. Exercise pipeline `AdvanceTo`, flush, pressure, and both-end completion when pipelines are selected.
- For native interop, test exact layouts/signatures, allocation/free pairing, callback rooting and late callbacks, disposal races, and every declared architecture or trimming/AOT deployment that can run.
- For multi-target projects, test each affected target; one target's success does not prove conditional code elsewhere.
- For serializers, reflection, trimming, or AOT, run the configured integration or publish checks rather than relying on unit mocks.
- For public packages, compile representative consumers and run API compatibility tooling when available.
- For performance claims, use the repository benchmark harness and compose `performance-engineering`.

## Interpret evidence correctly

- Restore proves dependency resolution, not compilation or behavior.
- Compilation on one target framework does not prove other targets or runtime identifiers.
- A passing unit project does not prove integration, packaging, reflection, trimming, or native interop.
- Coverage records execution, not correctness; preserve configured thresholds without inventing quotas.
- Mock verification proves interaction with the double, not the real framework or service.

## Recover and report

- Fix patch-caused focused failures before widening.
- If an SDK, workload, feed, runtime, platform, native dependency, or service stays missing, report it and run the strongest unaffected checks.
- Separate unrelated baseline failures; do not suppress warnings or weaken tests to obtain green output.
- Preserve seeds, dumps, logs, and inputs needed to reproduce nondeterministic failures without committing noise.

Primary references: [`dotnet test`](https://learn.microsoft.com/dotnet/core/tools/dotnet-test), [.NET testing overview](https://learn.microsoft.com/dotnet/core/testing/), [code analysis](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/overview), [package validation](https://learn.microsoft.com/dotnet/fundamentals/package-validation/overview), [async streams](https://learn.microsoft.com/dotnet/csharp/asynchronous-programming/generate-consume-asynchronous-stream).
