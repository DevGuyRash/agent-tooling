import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { openSession } from '../../../plugins/playwright-testing/runtime/session.mjs';
import { createEvidenceRun, readEvidenceRun, compareRuns } from '../../../plugins/playwright-testing/runtime/evidence.mjs';
import { capture } from '../../../plugins/playwright-testing/runtime/capture.mjs';
import { serveSurveyFixture } from './fixtures/browser-survey/server.mjs';

test('native capture scopes retain replayable selectors, locator descriptions and frame geometry', { skip: !process.env.PW_TEST_PLAYWRIGHT_PATH, timeout: 90000 }, async t => {
  const output = await mkdtemp(path.join(process.env.PW_CAPTURE_TEST_OUTPUT || tmpdir(), 'capture-scope-'));
  const fixture = await serveSurveyFixture();
  const writers = [];
  let session;
  t.after(async () => { await session?.close(); for (const writer of writers) await writer.close(); await fixture.close(); if (!process.env.PW_CAPTURE_TEST_OUTPUT) await rm(output, { recursive: true, force: true }); });
  session = await openSession({ playwrightPath: process.env.PW_TEST_PLAYWRIGHT_PATH, resourceRoot: path.join(output, 'resources'), viewport: { width: 900, height: 650 } });
  const { page } = session;
  await page.goto(`${fixture.url}/?scope=selection#measurements`, { waitUntil: 'load' });
  await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
  const run = await createEvidenceRun({ outputDir: path.join(output, 'selection') }); writers.push(run);
  const element = await capture(page, { run, target: '#measurements', diagnostics: false });
  assert.equal(element.status, 'complete');
  const nested = await capture(page, { run, scroll: { container: '#canvas-scroll', axis: 'both', maxFrames: 2, overlap: 0.25 }, diagnostics: false });
  assert.equal(nested.status, 'partial');
  const reproduction = { steps: ['Open Embedded observations'], target: 'Frame action in the embedded frame' };
  const framed = await capture(page, {
    run, target: page.frameLocator('iframe[name="embedded"]').getByRole('button', { name: 'Frame action', exact: true }).describe('Embedded action'),
    captureScope: reproduction, diagnostics: false,
  });
  assert.equal(framed.status, 'complete');
  const region = await capture(page, { run, region: { x: 10, y: 20, width: 100, height: 80 }, diagnostics: false });
  await run.close();
  const saved = await readEvidenceRun(run.outputDir, { limit: Infinity });
  const savedElement = saved.records.find(record => record.id === element.id);
  const savedNested = saved.records.find(record => record.id === nested.id);
  const savedFrame = saved.records.find(record => record.id === framed.id);
  const savedRegion = saved.records.find(record => record.id === region.id);
  assert.deepEqual(savedElement.captureScope, { mode: 'element', target: { kind: 'selector', selector: '#measurements' } });
  assert.equal(await page.locator(savedElement.captureScope.target.selector).getAttribute('id'), savedElement.selection.subject.identity.domId);
  assert.equal(savedElement.selection.subject.identity.domId, 'measurements');
  assert.ok(savedElement.selection.subject.boundsInPage.width > 0);
  assert.deepEqual(savedNested.captureScope.scroll, { container: { kind: 'selector', selector: '#canvas-scroll' }, axis: 'both', overlap: 0.25, maxFrames: 2 });
  const resumedContainer = page.locator(savedNested.captureScope.scroll.container.selector);
  assert.equal(await resumedContainer.getAttribute('id'), savedNested.selection.scrollContainer.identity.domId);
  assert.ok(savedNested.images.some(image => image.selection.scrollContainer.scroll.x > 0));
  assert.equal(savedFrame.captureScope.target.kind, 'locator');
  assert.equal(savedFrame.captureScope.target.description, 'Embedded action');
  assert.ok(savedFrame.captureScope.target.locator.includes('Frame action'));
  assert.ok(savedFrame.captureScope.target.locator.includes('iframe'));
  assert.deepEqual(savedFrame.captureScope.reproduction, reproduction);
  assert.equal(savedFrame.selection.subject.frame.name, 'embedded');
  assert.equal(savedFrame.selection.subject.frame.url, `${fixture.url}/frame`);
  assert.equal(savedFrame.selection.subject.frame.ancestry.length, 2);
  assert.equal(savedFrame.selection.subject.frame.ancestry[0].url, page.url());
  assert.ok(savedFrame.selection.subject.boundsInPage.x > savedFrame.selection.subject.boundsInFrame.x);
  assert.deepEqual(savedRegion.captureScope.region, { x: 10, y: 20, width: 100, height: 80 });
  for (const record of saved.records.filter(record => record.type === 'capture-progress')) {
    const final = saved.records.find(final => final.id === record.captureId);
    assert.deepEqual(record.captureScope, final.captureScope);
  }
  assert.ok(!JSON.stringify(saved).includes('_channel'));

  const optionsRun = await createEvidenceRun({ outputDir: path.join(output, 'options') }); writers.push(optionsRun);
  const screenshotOptions = { type: 'jpeg', quality: 72, fullPage: false, scale: 'css', animations: 'disabled', caret: 'hide', omitBackground: false, style: 'h1 { color: rgb(13, 50, 80) }', maskColor: '#ee55aa', mask: [page.locator('#delayed-image').describe('Illustration mask')] };
  const styled = await capture(page, { run: optionsRun, screenshotOptions, diagnostics: false });
  assert.equal(styled.status, 'complete');
  for (const key of ['type', 'quality', 'fullPage', 'scale', 'animations', 'caret', 'omitBackground', 'style', 'maskColor']) assert.equal(styled.captureScope.screenshotOptions[key], screenshotOptions[key]);
  assert.equal(styled.captureScope.screenshotOptions.mask[0].description, 'Illustration mask');
  assert.ok(styled.captureScope.screenshotOptions.mask[0].locator.includes('#delayed-image'));
  await optionsRun.close();

  const left = await createEvidenceRun({ outputDir: path.join(output, 'left') }); writers.push(left);
  const right = await createEvidenceRun({ outputDir: path.join(output, 'right') }); writers.push(right);
  const before = await capture(page, { run: left, target: 'h1', diagnostics: false });
  await page.locator('h1').evaluate(el => { el.style.width = '300px'; });
  const after = await capture(page, { run: right, target: 'h1', diagnostics: false });
  await capture(page, { run: right, target: '#details-tab', diagnostics: false });
  assert.notEqual(before.selection.subject.boundsInPage.width, after.selection.subject.boundsInPage.width);
  assert.deepEqual(before.captureScope, after.captureScope);
  await left.close(); await right.close();
  const compared = await compareRuns(left.outputDir, right.outputDir);
  assert.equal(compared.summary.matched, 1, 'Same selection remains comparable when its measured geometry changes');
  assert.equal(compared.summary.different, 1);
  assert.equal(compared.summary.onlyRight, 1, 'Another element on the same page is a separate comparison scope');
  await writeFile(path.join(output, 'scope-validation.json'), JSON.stringify({ element: savedElement.captureScope, nested: savedNested.captureScope, framed: savedFrame.captureScope, observedFrame: savedFrame.selection.subject, comparison: compared.summary }, null, 2));
  t.diagnostic(`Native selection reproduction and comparison evidence: ${output}`);
});
