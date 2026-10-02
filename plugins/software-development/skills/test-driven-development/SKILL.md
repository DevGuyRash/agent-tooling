---
name: test-driven-development
description: "Use when adding or changing executable behavior or fixing a known bug: a failing test that shows the gap, the smallest change that passes it, then cleanup. Excludes unknown-cause diagnosis and behavior-neutral refactors."
---

# Test-Driven Development

This skill builds on the [Software Development Foundation](../../foundation.md).

A failing test pins down a behavior before the code changes to provide it. Each increment is one observable behavior, and the next starts only after the current evidence is green.

Take the expected outcome from the governing requirement, public contract, or consumer, never from the implementation under repair. Test at the cheapest boundary that can disprove the behavior, preferring public seams to private details, and follow the repository's test layout, commands, and helpers. Tests assert outcomes rather than incidental call structure and stay deterministic at their layer.

Before changing production code, run the new test and confirm it fails for the reason you intend: it reaches its decisive assertion rather than failing on setup, compilation, or a test hook. A test that passes means the behavior already exists, the test does not discriminate, or the boundary is wrong. You SHALL NOT weaken a correct expectation to get a convenient failure.

Then change production code only as far as the behavior needs, and run the focused test and the surrounding suite. Unrelated failures are separate evidence whose expectations stay as they are. Refactor under green when the new code's duplication or unclear intent warrants it, or where it departs from the foundation.

When no honest failing test is available, say so rather than presenting the work as test-driven, and never delete existing work because its test was not written first; for generated code, spikes, unavailable automation, or already-written code, use the strongest feasible characterization.

Read [test selection](references/test-selection.md) when choosing among characterization, unit, integration, contract, property, or end-to-end tests, or when doubles and nondeterminism could make the evidence misleading.
