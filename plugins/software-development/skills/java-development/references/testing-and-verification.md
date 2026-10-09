# Java Testing and Verification

## Adapt to the existing test system

- Preserve JUnit 4, JUnit Jupiter, TestNG, Spock, or repository-specific conventions rather than migrating for preference.
- Reuse configured fixtures, extensions, parameterization, assertions, mocking tools, and test source sets.
- Test observable contracts. Avoid asserting incidental collection implementations, thread schedules, private methods, or exact exception text unless contractual.
- Keep unit, integration, functional, compatibility, and end-to-end tests in their configured tasks; a default `test` task may not run all of them.
- Make concurrent tests synchronize on events or bounded primitives rather than sleeps.

## Use a risk-shaped ladder

1. Compile the affected source set or module through the wrapper.
2. Run the focused test class or method using the repository's supported filter.
3. Run the affected module's full unit and relevant integration tasks.
4. Run configured formatting, Checkstyle, PMD, SpotBugs, Error Prone, nullness, coverage, or architecture checks.
5. Build and inspect the deployable or published artifact when packaging or public API changes.
6. Exercise the supported JDK/runtime matrix for changes that use or alter an API, language feature, dependency, or build setting whose availability differs across it.

Existing build configuration decides which checks are authoritative.

## Check specialized boundaries

- For overload or generic changes, compile representative callers as well as the implementation.
- For JPMS changes, test on the module path and check reflection/service loading.
- For serialization changes, test old/new fixtures or compatibility paths specified by the repository.
- For annotation processors, regenerate from a clean source state and verify generated output.
- For concurrency changes, combine deterministic lifecycle tests with stress or repeated execution; no finite run proves every schedule.
- For process wrappers, use a helper child that can fill stdout and stderr independently, wait for stdin EOF, hang, exit nonzero, and emit during termination. Synchronize on events and bounded deadlines; assert exit, both drains, termination policy, timeout overflow behavior, interruption status when contractual, and absence of surviving owned work.
- For fan-out or publisher changes, exercise multiple failures, a blocked or canceling participant, slow demand, full-buffer behavior, synchronous callback reentrancy, competing terminal actions, and cleanup failure. Verify every required outcome remains inspectable, the selected terminal cause is retained, and terminal completion occurs once.
- For performance claims, use a configured JMH or benchmark harness and route the measurement design to `performance-engineering`.

## Interpret evidence correctly

- Compilation on one JDK does not prove runtime compatibility with another.
- A passing unit task does not prove integration tasks, packaging, reflection, or service discovery.
- Java `assert` may be disabled and is not a substitute for a test assertion framework.
- Coverage is evidence of execution, not correctness; preserve repository thresholds without inventing new quotas.
- Mock verification proves interaction with the double, not compatibility with the real dependency.

## Recover and report

- Fix patch-caused focused failures before widening the suite.
- If a dependency, service, toolchain, or runtime stays missing, report the limitation and run the strongest unaffected checks.
- Separate an unrelated baseline failure from the patch; do not weaken tests or analyzers to obtain green output.
- Preserve failure seeds, temporary artifacts, and logs needed to reproduce nondeterministic failures without committing noise.

Primary references: [JUnit User Guide](https://docs.junit.org/current/user-guide/), [Maven Surefire](https://maven.apache.org/surefire/maven-surefire-plugin/), [Gradle Java testing](https://docs.gradle.org/current/userguide/java_testing.html).
