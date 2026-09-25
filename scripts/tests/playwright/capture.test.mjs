import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { discover, observeContext } from '../../../plugins/playwright-testing/runtime/discovery.mjs';
import { waitForReadiness } from '../../../plugins/playwright-testing/runtime/readiness.mjs';
import { capture } from '../../../plugins/playwright-testing/runtime/capture.mjs';
import { serveSurveyFixture } from './fixtures/browser-survey/server.mjs';

async function evidence(output) {
  const records = [];
  await mkdir(output, { recursive: true });
  return {
    records,
    async record(observation) { records.push(structuredClone(observation)); await writeFile(path.join(output, 'records.json'), JSON.stringify(records)); return observation; },
    async storeBlob(bytes, { extension, mime }) { const sha256 = createHash('sha256').update(bytes).digest('hex'), filename = `${sha256}.${extension}`; await writeFile(path.join(output, filename), bytes); return { path: filename, sha256, size: bytes.length, mime }; },
  };
}

test('capture option diagnostics fail before interacting with a page', async () => {
  await assert.rejects(capture(null, {}), /evidence run/);
  const run = { record() {}, storeBlob() {} };
  await assert.rejects(capture(null, { run, target: 'h1', region: {} }), /target or a region/);
  await assert.rejects(capture(null, { run, scroll: { axis: 'z' } }), /x, y or both/);
  await assert.rejects(capture(null, { run, screenshotOptions: { path: '/tmp/unowned.png' } }), /owns screenshot storage/);
  await assert.rejects(capture(null, { run, screenshotOptions: { clip: {} } }), /Use region/);
});

test('native discovery and capture retain meaningful states and bounded evidence', { skip: !process.env.PW_TEST_PLAYWRIGHT_PATH, timeout: 120000 }, async t => {
  const require = createRequire(import.meta.url);
  const { chromium } = require(process.env.PW_TEST_PLAYWRIGHT_PATH);
  const browser = await chromium.launch({ headless: true, channel: 'chromium', chromiumSandbox: true });
  const fixture = await serveSurveyFixture();
  const output = await mkdtemp(path.join(process.env.PW_CAPTURE_TEST_OUTPUT || tmpdir(), 'capture-tests-'));
  t.after(async () => { await browser.close(); await fixture.close(); if (!process.env.PW_CAPTURE_TEST_OUTPUT) await rm(output, { recursive: true, force: true }); });
  const fresh = async suffix => {
    const context = await browser.newContext({ viewport: { width: 900, height: 650 } });
    const page = await context.newPage();
    await page.goto(`${fixture.url}/${suffix || ''}`, { waitUntil: 'domcontentloaded' });
    return { context, page };
  };

  await t.test('discovery keeps duplicate destinations, frames, open shadows and new state', async () => {
    const { context, page } = await fresh();
    try {
      const result = await discover(page);
      const main = result.frames.find(frame => frame.parentId === null);
      assert.equal(main.links.filter(link => link.url === `${fixture.url}/next?filter=small#details`).length, 2);
      assert.ok(main.links.some(link => link.url === `${fixture.url}/next?filter=large#details`));
      assert.ok(main.links.some(link => link.url.includes('?shadow=yes#inside')));
      assert.ok(main.scrollContainers.some(item => item.domId === 'virtual'));
      assert.ok(main.controls.some(item => item.name === 'Shadow action'));
      const repeated = main.controls.filter(item => item.name === 'Repeated action');
      assert.equal(repeated.length, 2);
      assert.notEqual(repeated[0].id, repeated[1].id);
      for (const item of repeated) assert.equal(await page.locator(item.locator.css).count(), 1);
      assert.ok(result.frames.some(frame => frame.name === 'embedded' && frame.links.some(link => link.url.includes('?frame=yes#inside'))));
      assert.ok(!JSON.stringify(result).includes('synthetic-hidden-value'));
      await page.getByRole('tab', { name: 'Details', exact: true }).click();
      const changed = await discover(page);
      assert.ok(changed.url.endsWith('#details'));
      assert.ok(changed.frames[0].links.some(link => link.url.includes('?from=details#new')));
      assert.equal((await discover(page, { maxItems: 1 })).truncated, true);
    } finally { await context.close(); }
  });

  await t.test('readiness observes delayed assets while continuous requests remain active', async () => {
    const { context, page } = await fresh('?continuous');
    try {
      const result = await waitForReadiness(page, {
        timeout: 4000, check: async page => ({ ready: await page.getByRole('status').first().textContent() === 'Illustration ready', condition: 'The delayed image reported completion.' }),
      });
      assert.equal(result.status, 'ready');
      assert.equal(result.application.ready, true);
      assert.equal(result.frames[0].pendingImages.length, 0);
      assert.equal(await page.locator('#delayed-image').evaluate(img => img.naturalWidth), 240);
    } finally { await context.close(); }
  });

  await t.test('readiness reports unstable layout, callback deadlines and sampling limits', async () => {
    const { context, page } = await fresh('?unstable');
    try {
      const result = await waitForReadiness(page, { timeout: 350, stableFor: 1000, sampleInterval: 40 });
      assert.equal(result.status, 'unsettled');
      assert.equal(result.checks.find(check => check.name === 'layout').satisfied, false);
      let aborted = false;
      const callback = await waitForReadiness(page, { timeout: 150, layout: false, check: (_page, { signal }) => new Promise(resolve => signal.addEventListener('abort', () => { aborted = true; resolve(false); }, { once: true })) });
      assert.equal(callback.status, 'unsettled');
      assert.equal(aborted, true);
      const limited = await waitForReadiness(page, { timeout: 120, stableFor: 0, maxElements: 3 });
      assert.equal(limited.status, 'unsettled');
      assert.equal(limited.frames[0].truncated, true);
    } finally { await context.close(); }
  });

  await t.test('viewport and region images retain context with incremental observations', async () => {
    const { context, page } = await fresh();
    const run = await evidence(path.join(output, 'viewport'));
    try {
      const result = await capture(page, { run, label: 'Initial desktop view', state: { actions: ['Open Field Notes'], comparisonKey: 'initial' }, diagnostics: false });
      assert.equal(result.status, 'complete');
      assert.deepEqual(result.state.viewport, { width: 900, height: 650 });
      assert.deepEqual(result.state.actions, ['Open Field Notes']);
      assert.equal(result.images.length, 1);
      assert.equal(run.records[0].type, 'capture-progress');
      assert.equal(run.records.at(-1).type, 'capture');
      const region = await capture(page, { run, label: 'Header region', region: { x: 0, y: 0, width: 300, height: 160 }, diagnostics: false });
      const png = await readFile(path.join(output, 'viewport', region.images[0].path));
      assert.equal(png.readUInt32BE(16), 300); assert.equal(png.readUInt32BE(20), 160);
    } finally { await context.close(); }
  });

  await t.test('document and nested scroll sequences reach observed ends and restore position', async () => {
    const { context, page } = await fresh();
    const run = await evidence(path.join(output, 'scroll'));
    try {
      await page.evaluate(() => scrollTo({ top: 320, behavior: 'instant' }));
      const before = await page.evaluate(() => ({ x: scrollX, y: scrollY }));
      const result = await capture(page, { run, label: 'Document sequence', scroll: { maxFrames: 12 }, readiness: { stableFor: 50 }, diagnostics: false });
      assert.equal(result.status, 'complete', JSON.stringify(result.warnings));
      assert.equal(result.coverage.endReached, true);
      assert.ok(result.images.length > 1);
      assert.deepEqual(await page.evaluate(() => ({ x: scrollX, y: scrollY })), before);
      const container = page.locator('#canvas-scroll');
      await container.evaluate(el => el.scrollTo({ top: 70, left: 95, behavior: 'instant' }));
      const nestedBefore = await container.evaluate(el => ({ x: el.scrollLeft, y: el.scrollTop }));
      const nested = await capture(page, { run, label: 'Nested canvas', scroll: { container, axis: 'both', maxFrames: 20 }, readiness: { stableFor: 50 }, diagnostics: false });
      assert.equal(nested.status, 'complete', JSON.stringify(nested.warnings));
      assert.equal(nested.coverage.endReached, true);
      assert.ok(nested.images.some(image => image.position.x > 0));
      assert.ok(nested.images.some(image => image.position.y > 0));
      assert.deepEqual(await container.evaluate(el => ({ x: el.scrollLeft, y: el.scrollTop })), nestedBefore);
      assert.deepEqual(await page.evaluate(() => ({ x: scrollX, y: scrollY })), before);
      const virtual = await capture(page, { run, label: 'Virtual records', scroll: { container: '#virtual', maxFrames: 3 }, readiness: { stableFor: 50 }, diagnostics: false });
      assert.equal(virtual.status, 'partial');
      assert.equal(virtual.coverage.endReached, false);
      assert.equal(virtual.coverage.limitReached, true);
      assert.equal(virtual.images.length, 3);
      assert.equal(await page.locator('#virtual').evaluate(el => el.scrollTop), 0);
    } finally { await context.close(); }
  });

  await t.test('growing content and cancellation retain partial evidence', async () => {
    const { context, page } = await fresh('?growing');
    const run = await evidence(path.join(output, 'partial'));
    try {
      const result = await capture(page, { run, scroll: { container: '#grow', maxFrames: 4 }, readiness: { stableFor: 50 }, diagnostics: false });
      assert.equal(result.status, 'partial');
      assert.equal(result.coverage.endReached, false);
      assert.equal(result.images.length, 4);
      assert.equal(await page.locator('#grow').evaluate(el => el.scrollTop), 0);
      const controller = new AbortController();
      const cancelling = { ...run, async record(record) { const value = await run.record(record); if (record.type === 'capture-progress') controller.abort(); return value; } };
      const cancelled = await capture(page, { run: cancelling, scroll: true, signal: controller.signal, readiness: { stableFor: 50 }, diagnostics: false });
      assert.equal(cancelled.status, 'cancelled');
      assert.equal(cancelled.images.length, 1);
      assert.equal(run.records.at(-1).status, 'cancelled');
    } finally { await context.close(); }
  });

  await t.test('broken assets and missing targets remain observations with recoverable context', async () => {
    const { context, page } = await fresh('?broken-image');
    const run = await evidence(path.join(output, 'failure'));
    try {
      const ready = await waitForReadiness(page, { timeout: 3000 });
      assert.equal(ready.status, 'ready');
      assert.ok(ready.frames[0].failedImages.some(image => image.src.endsWith('/missing.png')));
      await page.evaluate(() => scrollTo({ top: 130, behavior: 'instant' }));
      const failed = await capture(page, { run, target: '#does-not-exist', timeout: 300, diagnostics: false });
      assert.equal(failed.status, 'partial');
      assert.equal(failed.images.length, 0);
      assert.equal(failed.state.url, page.url());
      assert.ok(failed.warnings.some(warning => warning.message.includes('does-not-exist')));
      assert.equal(await page.evaluate(() => scrollY), 130);
      const recovered = await capture(page, { run, target: page.getByRole('heading', { name: 'Field Notes', exact: true }), diagnostics: false });
      assert.equal(recovered.status, 'complete');
      assert.equal(recovered.images.length, 1);
      assert.equal(await page.evaluate(() => scrollY), 130);
    } finally { await context.close(); }
  });

  await t.test('context diagnostics bound errors, follow popups and detach cleanly', async () => {
    const context = await browser.newContext();
    const observer = observeContext(context, { limit: 5 });
    try {
      const page = await context.newPage();
      await page.goto(fixture.url);
      await page.getByRole('button', { name: 'Exercise expected error' }).click();
      await page.waitForFunction(() => document.querySelector('#expected-error'));
      const popupPromise = page.waitForEvent('popup');
      await page.getByRole('button', { name: 'Open companion' }).click();
      const popup = await popupPromise;
      await popup.waitForLoadState();
      await popup.evaluate(() => { console.error('Popup synthetic error'); });
      await popup.close();
      const snapshot = observer.snapshot();
      assert.equal(snapshot.observedPages, 2);
      assert.ok(snapshot.events.some(event => event.message === 'Popup synthetic error'));
      assert.equal(snapshot.attachedPages, 1);
      await page.evaluate(() => { for (let i = 0; i < 12; i++) console.warn(`Synthetic warning ${i}`); });
      assert.equal(observer.snapshot().events.length, 5);
      assert.ok(observer.snapshot().dropped >= 12);
      const count = observer.snapshot().events.at(-1).sequence;
      observer.close();
      await page.evaluate(() => console.error('After observer close'));
      assert.equal(observer.snapshot().events.at(-1).sequence, count);
      assert.equal(page.listenerCount('console'), 0);
      assert.equal(context.listenerCount('page'), 0);
      assert.equal(page.isClosed(), false);
    } finally { observer.close(); await context.close(); }
  });

  t.diagnostic(`Native capture evidence: ${output}`);
});
