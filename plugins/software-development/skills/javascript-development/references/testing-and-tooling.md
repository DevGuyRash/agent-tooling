# JavaScript Testing and Tooling

Load this reference when choosing verification, changing or reviewing dependencies or targets, or resolving disagreement between formatter, linter, tests, and runtime behavior.

## Test Observable Behavior

- Add or update the narrowest test that would fail for the original defect or missing behavior.
- Cover relevant boundaries: absent versus explicit values, falsy data, thrown versus rejected failures, duplicate calls, ordering, cancellation, and cleanup.
- For concurrency limits, hold admitted work behind controller-owned handshakes, observe the complete closed cohort before release, and prove eventual terminal completion. Do not infer a bound from start timestamps or a short sleep.
- For early aggregate settlement, timeout, or abort, keep the losing operation observable long enough to prove whether cancellation reached it and whether owned cleanup completed before return.
- Test public outcomes rather than private implementation structure unless that structure is itself contractual.
- Keep time, randomness, locale, timezone, environment variables, and network dependencies controlled when they affect results.
- Use fake timers only when the repository already supports them and advance both timer and promise work correctly.
- Restore global state, module mocks, listeners, and timers so test order does not matter.
- Isolate tests whose result depends on module evaluation or cache state in a fresh supported realm/process or through the repository's reset mechanism; cache-busting production specifiers are not a general test-isolation policy.

## Respect the Toolchain

- Infer the package manager from repository instructions, the lockfile, and workspace metadata. Do not mix lockfile ecosystems.
- Use existing package scripts and task runners before assembling equivalent ad hoc commands.
- Treat linter and formatter configuration as repository policy, not universal language truth.
- Keep generated bundles, coverage, declarations, and transpiled output untouched unless the repository tracks them or the task explicitly owns them.
- When a build transforms modules or syntax, verify the built artifact under a supported runtime when practical.
- If lint, static analysis, runtime, and tests disagree, identify whether they use different configs, environments, or source artifacts before weakening a check.

## Dependencies and Compatibility

- Add a dependency only when its behavior, maintenance, license, security, and bundle/runtime cost are justified for the task.
- Preserve dependency versus development-dependency placement and workspace ownership.
- Avoid unrelated upgrades and lockfile churn.
- Review the effective dependency diff, including transitive changes and install scripts, before claiming a safe update.
- Verify against the oldest supported target when using newly available syntax, APIs, or package export conditions.

## Completion Evidence

Report the focused tests, static checks, build/runtime checks, and targets exercised. Name checks skipped because of missing services, credentials, platform access, or time; do not convert absence of evidence into success.
