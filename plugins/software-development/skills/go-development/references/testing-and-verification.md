# Go Testing and Verification

## Follow the repository's test surface

- Preserve existing package choice, helpers, fixtures, golden-file policy, build tags, and third-party assertion libraries.
- Test observable behavior and contracts. Avoid coupling tests to goroutine schedules, map order, incidental allocation, or unexported structure without a reason.
- Use same-package or external-package tests according to the boundary being exercised; do not convert the suite for preference.
- Table-driven tests, subtests, examples, fuzz targets, and mocks are tools, not quotas.
- Keep test cleanup scoped with `t.Cleanup` and give parallel tests independent state.

## Use a risk-shaped ladder

1. Run formatting or the repository's formatting check on touched Go files.
2. Run the focused test or affected package through the repository command.
3. Run affected module tests, then the broader suite when shared or exported behavior changed.
4. Run configured vet, lint, generation, static analysis, or API checks.
5. Add race, fuzz, benchmark, cross-version, or cross-platform evidence for the changes each one covers.

`go test` may reuse cached successful results. Use the repository's cache-bypass convention, or `-count=1`, only when a fresh execution is necessary.

## Specialized checks

- Use `-race` for shared-memory changes on supported platforms; exercise the relevant workload rather than an unrelated empty path.
- Re-run a fuzz failure from its persisted seed/corpus before minimizing it. Keep regressions as deterministic tests.
- Benchmark performance claims with representative inputs, stable setup, multiple samples, and comparison tooling. Route broad optimization work to `performance-engineering`.
- Verify examples when they are executable documentation and public behavior changed.
- Run generator checks when generated output should remain clean.
- For public modules, compile and test against the declared version matrix when available.

## Interpret evidence correctly

- `gofmt` proves formatting, not behavior.
- Compilation proves type and build-constraint consistency for the selected target, not runtime correctness or other targets.
- A clean race run detects only races exercised in that run.
- `go vet` and linters are scoped analyzers, not complete correctness proofs.
- A passing package test does not prove callers or commands compile after an exported API change.

## Recover from failures

- If a focused check fails because of the patch, fix it before widening.
- If a declared toolchain, dependency, service, architecture, or cgo prerequisite stays missing, report that limitation and run the strongest unaffected checks.
- If an unrelated baseline failure appears, reproduce it without the changed path when safely possible; fix it if it blocks the change, else report it.

Primary references: [`testing` package](https://pkg.go.dev/testing), [`go test` command](https://pkg.go.dev/cmd/go#hdr-Test_packages), [fuzzing](https://go.dev/doc/security/fuzz), [race detector](https://go.dev/doc/articles/race_detector).
