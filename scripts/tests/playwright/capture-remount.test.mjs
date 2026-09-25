import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { openSession } from '../../../plugins/playwright-testing/runtime/session.mjs';
import { createEvidenceRun, readEvidenceRun } from '../../../plugins/playwright-testing/runtime/evidence.mjs';
import { capture } from '../../../plugins/playwright-testing/runtime/capture.mjs';

test('native remounted scroll targets restore by supported identity or retain an explicit partial result', { skip: !process.env.PW_TEST_PLAYWRIGHT_PATH, timeout: 60000 }, async t => {
  const output = await mkdtemp(path.join(process.env.PW_CAPTURE_TEST_OUTPUT || tmpdir(), 'capture-remount-'));
  let session;
  const writers = [], results = [];
  t.after(async () => { await session?.close(); for (const run of writers) await run.close(); if (!process.env.PW_CAPTURE_TEST_OUTPUT) await rm(output, { recursive: true, force: true }); });
  session = await openSession({ playwrightPath: process.env.PW_TEST_PLAYWRIGHT_PATH, resourceRoot: path.join(output, 'resources'), viewport: { width: 600, height: 400 } });
  const { page } = session;
  for (const scenario of ['same-identity', 'changed-identity']) {
    await page.setContent(`<title>Remounting scroller</title><style>.scroller{height:120px;width:240px;overflow:auto}#content{height:480px;background:linear-gradient(red,blue)}</style><div class="scroller" id="scroll"><div id="content"></div></div><script>window.armed=false;document.querySelector('.scroller').addEventListener('scroll',event=>{if(!window.armed)return;window.armed=false;const original=event.currentTarget;const replacement=original.cloneNode(true);if(${JSON.stringify(scenario)}==='changed-identity')replacement.id='different-target';original.replaceWith(replacement);window.remounted=true;});</script>`);
    await page.locator('.scroller').evaluate(el => { el.scrollTop = 75; });
    await page.waitForFunction(() => document.querySelector('.scroller').scrollTop === 75);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.evaluate(() => { window.armed = true; });
    const run = await createEvidenceRun({ outputDir: path.join(output, scenario) }); writers.push(run);
    const result = await capture(page, { run, label: scenario, scroll: { container: '.scroller', maxFrames: 10 }, readiness: { stableFor: 50 } });
    assert.equal(await page.evaluate(() => window.remounted), true);
    assert.equal(result.coverage.endReached, true);
    const after = await page.locator('.scroller').evaluate(el => ({ id: el.id, y: el.scrollTop }));
    if (scenario === 'same-identity') {
      assert.equal(after.y, 75, 'The live replacement receives the original scroll position');
      assert.equal(result.status, 'complete');
      assert.equal(result.restoration.container.recovered, true);
      assert.equal(result.warnings.length, 0);
    } else {
      assert.equal(after.id, 'different-target');
      assert.equal(result.status, 'partial');
      assert.equal(result.restoration.container.status, 'partial');
      assert.ok(result.warnings.some(warning => warning.stage === 'scroll-restoration' && warning.message.includes('matching native identity')));
      assert.deepEqual(result.restoration.container.expected, { x: 0, y: 75 });
      assert.equal(result.restoration.container.observed.y, after.y);
    }
    await run.close();
    const saved = await readEvidenceRun(run.outputDir, { id: result.id });
    assert.deepEqual(saved.records[0].restoration, result.restoration);
    assert.equal(saved.records[0].captureScope.scroll.container.selector, '.scroller');
    results.push({ scenario, after, status: result.status, warnings: result.warnings, restoration: result.restoration });
  }
  await writeFile(path.join(output, 'restoration-validation.json'), JSON.stringify(results, null, 2));
  t.diagnostic(`Actual remount and restoration evidence: ${output}`);
});
