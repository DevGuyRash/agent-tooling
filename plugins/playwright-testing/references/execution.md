# Browser execution

The complete plugin provides `runtime/index.mjs` and `scripts/browser-tools.mjs`. Both skills reach them through `../../` from their skill directory. Resolve `<skills-file-root>` to the directory containing the invoked `SKILL.md` before running the commands below. The JavaScript objects returned by the runtime are ordinary Playwright objects.

## Runtime selection and setup

Use the application's compatible Playwright installation. `projectDir` establishes package resolution and defaults to the current working directory. `playwrightPath` selects an installed `playwright`, `@playwright/test`, or `playwright-core` package directory or entry file explicitly. A relative explicit path is resolved from `projectDir`. This keeps unrelated working directories and an installed plugin's own dependencies from selecting the wrong runtime.

```sh
node "<skills-file-root>/../../scripts/browser-tools.mjs" doctor --project "/path/to/application"
node "<skills-file-root>/../../scripts/browser-tools.mjs" doctor --playwright "/path/to/runtime/node_modules/playwright" --devices
```

Diagnostics report the actual installation and available platform prerequisites. Device names come from that installation's registry. Browser package resolution and the presence of a binary are setup observations; launching the requested configuration establishes runtime availability.

When standalone setup is part of the authorized work, this pinned recipe installs Playwright 1.63.0 and its full Chromium binary. Use Node.js 20 or later, matching [the package's declared runtime](https://github.com/microsoft/playwright/blob/v1.63.0/packages/playwright/package.json).

```sh
npm install --prefix "/path/to/owned/playwright-runtime" --save-exact playwright@1.63.0
node "/path/to/owned/playwright-runtime/node_modules/playwright/cli.js" install chromium
```

Supply the resulting package directory through `--playwright` or `playwrightPath`. Choose additional engines through the same Playwright installation. [Browser installation](https://playwright.dev/docs/browsers) documents binary and OS dependencies. Optional Linux headed setup is described in [platform isolation](isolation.md). The plugin reports missing setup and does not install dependencies while launching a session.

## Session helpers

```js
import { withSession } from '/absolute/plugin/path/runtime/index.mjs';

await withSession({
  projectDir: '/path/to/application',
  presentation: 'headless',
  browser: 'chromium',
  viewport: { width: 1440, height: 900 },
  contextOptions: { colorScheme: 'dark' },
}, async ({ page, context, info }) => {
  await page.goto('https://example.com/', { waitUntil: 'domcontentloaded' });
  // Use normal Playwright interactions and assertions for the assignment.
  console.log(JSON.stringify(info));
});
```

`openSession(options)` returns `{ browser, context, page, info, close }`. `withSession(options, callback)` closes owned resources when the callback completes or throws. For manual lifetime management, call `close()` in `finally`. Close or dispose additional resources owned by the script before closing the session. Flush videos by closing the context, then save them while the browser connection remains open; see the [video pattern](survey-patterns.md#traces-and-video).

| Option | Behavior |
|---|---|
| `presentation` | `headless` by default; `isolated-headed` requests an isolated display/session. |
| `browser`, `channel` | Engine from the installed runtime; a device's default engine applies when no engine is supplied. Chromium defaults to channel `chromium`, using its full binary in both presentations. |
| `device` | Name from the installed Playwright device registry. |
| `contextOptions` | Native context settings merged over the device descriptor. |
| `viewport`, `screen` | Explicit dimensions override the corresponding descriptor/context values. |
| `display` | Optional native display dimensions; otherwise derived from screen or viewport. |
| `launchOptions` | Native launch options; `presentation` owns headless/headed selection. |
| `provider` | Configured isolated session provider, described in [platform isolation](isolation.md). |
| `resourceRoot`, `artifactDir`, `signal` | Private execution-resource root, retained session diagnostics directory, and cancellation input. |

The device descriptor is applied first, then `contextOptions`, then explicit `viewport` and `screen`. The information record retains actual versions, host and rendering OS, backend, requested and observed geometry, and emulation settings. The initial geometry records Playwright viewport dimensions separately from the initial document layout viewport; captured states retain their own later measurements. Use this context with screenshots when comparing environments. Emulating a device does not change the host OS or reproduce its physical hardware.

For Chromium, the default full-binary `chromium` channel uses [new headless mode](https://playwright.dev/docs/browsers#chromium-new-headless-mode). Set an explicit supported channel when a branded browser is material to the test. [Emulation](https://playwright.dev/docs/emulation) describes which browser properties the device and context options control.

When `artifactDir` is supplied, `info.diagnosticPath` identifies a retained session receipt. It records sanitized environment information and cleanup status. `resourceRoot` owns the temporary execution directory; successful closure removes that directory while retaining diagnostics and evidence.

## Existing test commands

Preserve the project's test runner, arguments, and working directory. `isolate-run` supplies an isolated headed environment around the command; the command retains its own runner configuration.

```sh
node "<skills-file-root>/../../scripts/browser-tools.mjs" isolate-run --screen 1600x1000 --timeout-ms 120000 -- node "./node_modules/@playwright/test/cli.js" test --headed
```

The JavaScript equivalent is `runIsolated(command, args, options)`, returning `{ exitCode, signal, info }`. Supply `cwd` for a working directory different from the caller's. Headless Playwright Test runs normally through the project's existing command. A headed runner still needs its headed flag or configuration when wrapped.

## Capture and evidence commands

```sh
node "<skills-file-root>/../../scripts/browser-tools.mjs" capture "https://example.com/" --output "/path/to/new-run" --project "/path/to/application" --width 1440 --height 900
node "<skills-file-root>/../../scripts/browser-tools.mjs" summary --run "/path/to/run" --limit 10 --type capture --details
node "<skills-file-root>/../../scripts/browser-tools.mjs" gallery --run "/path/to/run"
node "<skills-file-root>/../../scripts/browser-tools.mjs" import --input "/path/to/capture-collection" --output "/path/to/new-run"
node "<skills-file-root>/../../scripts/browser-tools.mjs" compare --left "/path/to/before" --right "/path/to/after" --output "/path/to/comparison"
```

`capture` is a useful single-state entry point. Use ordinary JavaScript with the [capture and discovery helpers](survey-patterns.md) for task-specific journeys, readiness, state selection, or resumption. Shared helpers retain local files and evidence metadata; publication is a separate action.

The runtime keeps browser socket/profile temporary files in a separate short owned directory so nested resource paths remain usable. `info.temporaryDirectory` identifies that directory; `temporaryRoot` selects another suitable short parent when needed. Cleanup validates reciprocal ownership before removing it. Startup errors carry concise causes and recovery hints; when diagnostics are retained, `error.diagnosticPath` identifies the session receipt and its `failure` and `cleanup` observations.
