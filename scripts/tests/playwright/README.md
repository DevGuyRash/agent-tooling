# Playwright plugin tests

The suite exercises the maintained plugin through its public JavaScript and CLI interfaces. Supply an installed Playwright package and browser binaries explicitly. Native Linux cases use Xvfb, xwininfo, and the selected browser's system dependencies; video qualification also uses ffprobe. The plugin's [execution reference](../../../plugins/playwright-testing/references/execution.md) owns runtime setup.

From the repository root:

```sh
PW_TEST_PLAYWRIGHT_PATH=/absolute/runtime/node_modules/playwright \
  node --test --test-concurrency=1 scripts/tests/playwright/*.test.mjs
node --test scripts/tests/playwright/fixtures/evaluation/fixture.test.mjs
```

Set `PW_TEST_CAPTURE_COLLECTION` to a supplied capture directory to include the large import and byte-deduplication fixture. Tests use private temporary directories; retained inspection output can use the corresponding test's output variable where supplied. Qualification records and captures belong in the repository's ignored local context directory.

The evaluation fixtures supply independent application instances and ordinary task inputs for a site survey, saved-session investigation, and headed test repair. Their README describes the server interface. Comparative assignments, condition identities, expected findings, and participant outputs remain outside the shipped plugin and outside task participants' input packets.

The plugin's `scripts/qualify-session.mjs` is the portable consumer smoke command. [Platform isolation](../../../plugins/playwright-testing/references/isolation.md) owns the native window, foreground, lifecycle, and provider observations needed on each host.
