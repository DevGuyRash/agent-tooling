# Authentication and storage

Choose fixtures from where the application actually keeps the session. Playwright Test's ordinary browser-context fixture is fresh for each test. A persistent profile, attached browser, reused context, server account, or shared backend carries state across tests independently of that fixture.

## Snapshot support

The following options are part of [Playwright 1.63's BrowserContext API](https://github.com/microsoft/playwright/blob/v1.63.0/docs/src/api/class-browsercontext.md#async-method-browsercontextstoragestate). The [current API reference](https://playwright.dev/docs/api/class-browsercontext#browser-context-storage-state) identifies changes for other installed versions.

| State | Snapshot interface | Material limit |
|---|---|---|
| Cookies and local storage | `context.storageState()` | Session expiry and server-side account state still apply. |
| IndexedDB | `context.storageState({ indexedDB: true })`, available since 1.51 | Enable it when the application needs this data, including authentication tokens kept there. |
| Origin-private file system | `context.storageState({ opfs: true })`, available since 1.63 | Ephemeral WebKit contexts do not support OPFS in this release. |
| Virtual WebAuthn credentials | `context.storageState({ credentials: true })`, available since 1.61 | Contains virtual credential private keys. Restoring it installs the virtual authenticator and replaces native authenticator handling in that context. |

Select the options the application needs. For a synthetic application using IndexedDB and origin-private files:

```js
const state = await context.storageState({ indexedDB: true, opfs: true });
const restored = await browser.newContext({ storageState: state });
try {
  const page = await restored.newPage();
  await page.goto(appURL);
  // Assert the actual session and durable application records here.
} finally {
  await restored.close();
}
```

`context.setStorageState(state)` replaces the current context's cookies, local storage, IndexedDB, origin-private files, and virtual credentials. Use it deliberately for a state replacement; creating a fresh context usually makes fixture ownership clearer.

Session storage requires an explicit fixture or initialization script. Client certificates, extension storage, a browser profile, and hardware-backed or OS-managed authenticators have separate setup and lifecycle. Restoring a virtual credential tests the virtual ceremony; physical keys, biometric UI, and platform account integration require observations at their actual native boundary.

## Virtual passkeys

The [Credentials API](https://playwright.dev/docs/api/class-credentials) owns virtual WebAuthn behavior. Install it before a page first uses `navigator.credentials`. A synthetic test can let the application register a passkey, then retain the virtual credential in its state:

```js
await context.credentials.install();
await page.goto(registrationURL);
await page.getByRole('button', { name: 'Create a passkey' }).click();
// Assert the application's registration outcome before saving its fixture.
const state = await context.storageState({ credentials: true });
const later = await browser.newContext({ storageState: state });
```

Seeding keys with `context.credentials.create()` prepares the authenticator's records; `install()` enables interception. The relying party's server must recognize the corresponding public key for an authentication test to succeed. See the [versioned API and examples](https://github.com/microsoft/playwright/blob/v1.63.0/docs/src/api/class-credentials.md).

## Fixture custody and verification

Treat state files, profiles, virtual credential private keys, traces, videos, and captured network data according to the session they contain. Store required fixtures in an owned private location and share scoped evidence that serves the test. Use synthetic accounts and values where they establish the same property.

Verify restoration through the consuming application. A state file existing or an API accepting it does not establish a logged-in session or a durable business record. [Playwright's authentication guide](https://playwright.dev/docs/auth) covers setup projects, account isolation, and session storage recipes.
