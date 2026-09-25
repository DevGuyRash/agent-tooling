# Playwright E2E patterns

These examples illustrate properties worth observing. Adapt their domain, fixture, and boundary to the application.

## A durable outcome

This test assumes an application-owned seed fixture and a UI whose order number is a stable identity. The fixture creates an account and cart; the browser submits the order and retrieves the result after a reload.

```js
import { test, expect } from '@playwright/test';

test('a submitted order remains available in order history', async ({ page, request }) => {
  const seed = await request.post('/test/seed-order', {
    data: { runId: crypto.randomUUID() },
  });
  expect(seed.ok()).toBeTruthy();
  const { checkoutURL } = await seed.json();

  await page.goto(checkoutURL);
  await page.getByRole('button', { name: 'Place order', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Order confirmed');
  const orderId = (await page.getByLabel('Order number').textContent())?.trim();
  expect(orderId).toBeTruthy();

  await page.goto('/orders');
  await page.reload();
  await expect(page.getByRole('link', { name: orderId, exact: true })).toBeVisible();
});
```

A confirmation is intermediate evidence. If the promised result crosses another material boundary, such as delivery to a provider, observe that result through the provider or its actual consuming interface. Describe substituted seams where they limit the claim. Remove seeded records through the fixture's owned cleanup when the test environment persists.

## Wait for the relevant transition

Playwright's locators and web-first assertions retry observable conditions. When several outcomes matter, inspect the outcomes the application actually presents. Include relevant last observations in the diagnostic; define the outcomes from the page and assignment rather than a universal state roster.

```js
await page.getByRole('button', { name: 'Save preferences' }).click();
await expect(page.getByRole('status')).toHaveText('Preferences saved');
await page.reload();
await expect(page.getByLabel('Email summaries')).toBeChecked();
```

Use `expect.poll` for an external observation and a bounded locator assertion for a browser state. Loading indicators, animations, and periodic network activity can persist after the desired condition is ready. A deliberate elapsed-time assertion is appropriate when time itself is the product contract; an arbitrary pause usually hides the condition the test needs.

## Repeated controls and maintained selectors

Scope a semantic locator by the item identity when several controls share a name:

```js
const account = page.getByRole('row').filter({ hasText: 'Account 4281' });
await expect(account).toHaveCount(1);
await account.getByRole('button', { name: 'Edit', exact: true }).click();
```

A domain helper can centralize unstable third-party selectors while keeping its target visible in diagnostics. A selector contract test should establish that it found the intended element. A locator resolving somewhere is weaker evidence than identifying the right account and operation.

## Failure evidence

Playwright Test can retain traces and screenshots through its existing configuration:

```js
import { defineConfig } from '@playwright/test';

export default defineConfig({
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
```

Merge relevant settings into the application's existing configuration. Keep retries consistent with the test's purpose; a retry can provide evidence about instability without erasing the initial failure. Add the observation that makes diagnosis possible, such as the item identity, requested state, actual URL, or last relevant response. [Trace Viewer](https://playwright.dev/docs/trace-viewer) provides step, DOM, screenshot, and network context.

Unexpected product-owned page errors and failed requests can be part of a test's outcome where they matter. Preserve expected fixture failures and infrastructure failures distinctly. Review artifacts before sharing because they can include session material or unrelated private content.
