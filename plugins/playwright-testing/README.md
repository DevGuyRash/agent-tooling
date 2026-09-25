# Playwright Testing

Two skills share browser execution and evidence helpers:

- **Playwright Testing** designs, runs, reviews, and diagnoses browser tests with assertions that support the claimed outcome.
- **Browser Survey** explores application states, captures reproducible evidence, and organizes or compares captures for people and agents.

The package supplies a Node.js API and CLI around the task's compatible Playwright installation. Native headless execution is the default. Optional isolated headed backends keep GUI work off the active desktop and own their teardown. The platform implementations and qualification boundaries are described in [platform isolation](references/isolation.md).

Start with [execution and setup](references/execution.md), or use the relevant skill entry: [Playwright Testing](skills/playwright-testing/SKILL.md) and [Browser Survey](skills/browser-survey/SKILL.md). [Survey patterns](references/survey-patterns.md) describe discovery and evidence composition. [Authentication and storage](references/authentication.md) covers versioned browser-state support.

Install the complete plugin so both skills can resolve their shared runtime and references. Both Codex and Claude host packages contain the same execution resources. Browser binaries and optional display or session providers are runtime dependencies selected for the target environment.
