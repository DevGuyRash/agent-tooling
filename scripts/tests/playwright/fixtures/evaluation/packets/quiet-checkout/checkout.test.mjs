import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { assertQuietEnvironment } from './quiet-launch.mjs';

test('two notebooks produce a durable receipt', { timeout: 30_000 }, async () => {
  const display = await assertQuietEnvironment();
  if (!process.env.PW_TEST_PLAYWRIGHT_PATH) throw new Error('Set PW_TEST_PLAYWRIGHT_PATH to the supplied Playwright package.');
  const origin = new URL(process.env.EVAL_ORIGIN);
  if (origin.protocol !== 'http:' || origin.hostname !== '127.0.0.1') throw new Error('EVAL_ORIGIN must point to the supplied local checkout.');
  const { chromium } = createRequire(import.meta.url)(process.env.PW_TEST_PLAYWRIGHT_PATH);
  const parent = resolve(process.env.EVAL_OUTPUT_DIR ?? 'artifacts'); await mkdir(parent, { recursive: true });
  const output = await mkdtemp(join(parent, 'checkout-'));
  let browser, context, page, failure;
  const observations = { presentation: 'headed', display, receiptUrl: null, reloaded: false };
  try {
    browser = await chromium.launch({ headless: false, channel: 'chromium', chromiumSandbox: true, env: { ...process.env, XDG_SESSION_TYPE: 'x11', GDK_BACKEND: 'x11' } });
    observations.browserVersion = browser.version();
    context = await browser.newContext({ viewport: { width: 1100, height: 820 } });
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
    page = await context.newPage();
    await page.goto(origin.href);
    await page.getByRole('spinbutton', { name: 'Quantity' }).fill('2');
    assert.equal(await page.getByLabel('Order total').textContent(), '$84.00');
    await page.getByRole('button', { name: 'Complete purchase', exact: true }).click();
    await page.waitForURL(/\/receipt\/R-\d{4}$/);
    observations.receiptUrl = page.url();
    await page.getByRole('heading', { name: 'Order confirmed', exact: true }).waitFor({ timeout: 2000 });
    assert.equal(await page.getByTestId('receipt-quantity').textContent(), '2');
    assert.equal(await page.getByTestId('receipt-total').textContent(), '$84.00');
    const receiptId = await page.getByTestId('receipt-id').textContent();
    await page.reload();
    assert.equal(page.url(), observations.receiptUrl);
    assert.equal(await page.getByTestId('receipt-id').textContent(), receiptId);
    assert.equal(await page.getByTestId('receipt-quantity').textContent(), '2');
    assert.equal(await page.getByTestId('receipt-total').textContent(), '$84.00');
    observations.reloaded = true;
    await page.screenshot({ path: join(output, 'receipt.png') });
  } catch (error) {
    failure = error; observations.failure = error.message;
    if (page) await page.screenshot({ path: join(output, 'failure.png') }).catch(() => {});
  } finally {
    if (context) await context.tracing.stop({ path: join(output, 'trace.zip') }).catch(() => {});
    if (browser) await browser.close();
    await writeFile(join(output, 'observations.json'), `${JSON.stringify(observations, null, 2)}\n`);
    process.stdout.write(`Evidence: ${output}\n`);
  }
  if (failure) throw failure;
});
