import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { openSession, capture, createEvidenceRun, compareRuns } from '../../../plugins/playwright-testing/runtime/index.mjs';

async function fixture(t) {
  const output = await mkdtemp(path.join(tmpdir(), 'capture-context-'));
  const writers = [];
  let session;
  t.after(async () => {
    await session?.close();
    for (const run of writers) await run.close();
    await rm(output, { recursive: true, force: true });
  });
  session = await openSession({ playwrightPath: process.env.PW_TEST_PLAYWRIGHT_PATH, viewport: { width: 700, height: 500 }, resourceRoot: path.join(output, 'resources') });
  const record = async (name, options) => {
    const run = await createEvidenceRun({ outputDir: path.join(output, name) });
    writers.push(run);
    const result = await capture(session.page, { run, diagnostics: false, readiness: { stableFor: 50 }, ...options });
    await run.finish();
    await run.close();
    return { result, outputDir: run.outputDir };
  };
  return { ...session, record };
}

test('comparison distinguishes a selector in separate frames and still pairs a moved subject in the same frame', { skip: !process.env.PW_TEST_PLAYWRIGHT_PATH, timeout: 60000 }, async t => {
  const { page, record } = await fixture(t);
  await page.setContent('<title>Framed subjects</title><style>iframe{width:200px;height:200px;border:0}</style><iframe name="left" srcdoc="<style>body{margin:0}#subject{width:100px;height:100px;background:red}</style><div id=subject></div>"></iframe><iframe name="right" srcdoc="<style>body{margin:0}#subject{width:100px;height:100px;background:blue}</style><div id=subject></div>"></iframe>');
  const left = page.frame({ name: 'left' }).locator('#subject');
  const right = page.frame({ name: 'right' }).locator('#subject');
  const before = await record('left', { target: left });
  const other = await record('right', { target: right });
  const separated = await compareRuns(before.outputDir, other.outputDir);
  assert.equal(separated.summary.matched, 0, 'Frame-scoped targets are different subjects despite identical local selectors.');
  assert.equal(separated.summary.onlyLeft, 1);
  assert.equal(separated.summary.onlyRight, 1);
  await left.evaluate(element => { element.style.marginTop = '25px'; element.style.background = 'green'; });
  const moved = await record('left-moved', { target: left });
  const corresponding = await compareRuns(before.outputDir, moved.outputDir);
  assert.equal(corresponding.summary.matched, 1, 'Measured element geometry is not its frame identity.');
  assert.equal(corresponding.summary.different, 1, 'The retained pixels expose the changed subject.');
  const authored = await compareRuns(before.outputDir, other.outputDir, { key: () => 'caller-selected-pair' });
  assert.equal(authored.summary.matched, 1, 'The caller can deliberately select a cross-frame comparison.');
});

test('element captures report a remounted ancestor whose original scroll position was zero or nonzero', { skip: !process.env.PW_TEST_PLAYWRIGHT_PATH, timeout: 60000 }, async t => {
  const { page, record } = await fixture(t);
  for (const initial of [0, 75]) {
    await page.setContent('<title>Remounted ancestor</title><style>#scroll{width:250px;height:120px;overflow:auto}#spacer{height:400px}#target{height:80px;background:green}#tail{height:120px}</style><div id="scroll"><div id="spacer"></div><div id="target">Selected target</div><div id="tail"></div></div><script>window.armed=false;document.querySelector("#scroll").addEventListener("scroll",event=>{if(!window.armed)return;window.armed=false;const original=event.currentTarget;const replacement=original.cloneNode(true);const y=original.scrollTop;original.replaceWith(replacement);replacement.scrollTop=y;window.remounted=true;});</script>');
    await page.locator('#scroll').evaluate((element, y) => { element.scrollTop = y; }, initial);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.evaluate(() => { window.armed = true; });
    const { result } = await record(`ancestor-${initial}`, { target: '#target' });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.evaluate(() => window.remounted), true);
    assert.ok(result.images.length, 'Completed evidence survives a restoration failure.');
    const actual = await page.locator('#scroll').evaluate(element => element.scrollTop);
    if (actual !== initial) {
      assert.equal(result.status, 'partial', 'An altered live scroll position cannot be reported as fully restored.');
      const warning = result.warnings.find(item => item.stage === 'scroll-restoration' && item.identity?.domId === 'scroll');
      assert.deepEqual(warning?.expected, { x: 0, y: initial });
    } else assert.equal(result.status, 'complete');
  }
});
