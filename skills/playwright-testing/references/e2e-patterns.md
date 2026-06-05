# Playwright E2E Patterns

Use these examples as adaptable patterns, not as copy-paste contracts. Preserve the outcome, selector-ownership, deterministic setup, and artifact ideas while changing domain details to match the app under test.

## Outcome Journey Template

Use this for app-owned journeys such as checkout, record creation, dashboard filtering, or settings updates.

```js
test("user completes checkout and sees the order in history", async ({ page, request }) => {
  await test.step("arrange account and cart through API", async () => {
    // Seed deterministic state.
  });

  await test.step("open checkout", async () => {
    await page.goto("/checkout");
    await expect(page.getByRole("heading", { name: "Checkout" })).toBeVisible();
  });

  await test.step("submit order", async () => {
    await page.getByRole("button", { name: "Place order" }).click();
  });

  await test.step("assert product outcome", async () => {
    await expect(page.getByRole("status")).toContainText("Order confirmed");
  });
});
```

## Selector Canary Template

Use this for uncontrolled, generated, third-party, frequently changing, or business-critical selectors. `findSemanticTarget` below is an illustrative helper, not a Playwright API; provide your own that tries each candidate locator and records which one matched.

```js
test("checkout submit selector still resolves", async ({ page }, testInfo) => {
  await page.goto("/checkout");

  const result = await findSemanticTarget(page, "submitOrder", [
    () => page.getByRole("button", { name: "Place order" }),
    () => page.getByTestId("submit-order"),
  ]);

  await testInfo.attach("selector-submitOrder.json", {
    body: JSON.stringify(result.report, null, 2),
    contentType: "application/json",
  });

  expect(result.matched, result.failureMessage).toBeTruthy();
  await expect(result.locator).toBeEnabled();
});
```

## State Classifier Template

For unstable surfaces, return structured state instead of booleans.

```js
async function classifyPageState(page) {
  const base = {
    url: page.url(),
    title: await page.title(),
    matchedSelectors: [],
    notes: [],
  };

  const signIn = page.getByRole("button", { name: "Sign in" });
  if (await signIn.isVisible().catch(() => false)) {
    return {
      ...base,
      kind: "login_required",
      matchedSelectors: ["role=button[name='Sign in']"],
      notes: ["Sign-in action is visible before the tested surface is ready."],
    };
  }

  const dashboard = page.getByRole("heading", { name: "Dashboard" });
  if (await dashboard.isVisible().catch(() => false)) {
    return {
      ...base,
      kind: "ready",
      matchedSelectors: ["role=heading[name='Dashboard']"],
    };
  }

  return {
    ...base,
    kind: "unknown",
    notes: ["No known ready, login, error, or blocked-state selector matched."],
  };
}
```

## Third-Party Or Provider Surfaces

For third-party or frequently changing UIs, use domain-specific semantic names inside that helper layer. Examples may include chat-provider names such as `composer`, `sendButton`, or `assistantMessage`, but those should not be canonical generic examples for app-owned tests.

## Good And Bad Examples

Bad:

```js
await page.locator(".card > div:nth-child(3) button").click();
```

Good for app-owned UI:

```js
await page.getByRole("button", { name: "Place order" }).click();
```

Good for third-party UI:

```js
await selectors.find("submitOrder").click();
```

Bad:

```js
await page.waitForTimeout(5000);
```

Good:

```js
await expect(page.getByRole("status")).toContainText("Saved");
```

Bad: asserting a marketing tagline, third-party incidental text, generated class, or visual layout detail that is not the product contract.

Good: asserting an app-owned confirmation, status, total, ID, or durable semantic state.

## Review Checklist

- Does the test prove a user/product outcome?
- Is e2e the right tier?
- Are app-owned selectors role-based or stable?
- Are third-party selectors centralized?
- Are selector canaries separated from journeys?
- Does every wait have a named outcome?
- Are auth and data setup deterministic?
- Are page states classified where needed?
- Do failure artifacts identify the broken outcome or semantic selector?
