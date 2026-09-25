#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFile, stat } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { parseArgs } from 'node:util';

const help = `Usage: node qualify-session.mjs --output DIR [options]
  --presentation headless|isolated-headed  Default: headless
  --project DIR                            Application runtime resolution
  --playwright PATH                        Explicit Playwright package
  --browser ENGINE                         Default: chromium
  --provider MODULE                        Configured isolated session provider
  --width N --height N                      Default: 1280 x 800
  --timeout-ms N                           Default: 60000
Checks synthetic page/popup interaction, capture, and owned cleanup.
Native foreground and window-affinity checks are listed with the result.`;

function positive(value, name) {
  const result = Number(value);
  if (!Number.isInteger(result) || result < 1) throw new Error(`${name} must be a positive integer.`);
  return result;
}

const mainHTML = `<!doctype html><html lang="en"><meta charset="utf-8"><title>Browser session qualification</title>
<style>body{font:18px system-ui;margin:40px;max-width:900px;color:#172033;background:#eef3fb}main{background:white;border:1px solid #cad5e6;border-radius:16px;padding:28px}button,input{font:inherit;padding:12px;margin:8px 8px 8px 0}button{cursor:pointer}output{display:block;margin:16px 0;color:#185938}</style>
<main><h1>Browser session qualification</h1><p>This synthetic page checks pointer input, keyboard input, popup rendering, and screenshots.</p>
<form><label for="message">Your message</label><br><input id="message" autocomplete="off"><button>Keep message</button></form><output role="status" id="saved">Waiting for keyboard input</output>
<button type="button" id="pointer">Check pointer</button><output id="pointer-status">Waiting for pointer input</output><button type="button" id="popup">Open popup</button></main>
<script>document.querySelector('form').addEventListener('submit',event=>{event.preventDefault();document.querySelector('#saved').textContent=document.querySelector('#message').value});document.querySelector('#pointer').addEventListener('click',event=>{document.querySelector('#pointer-status').textContent='Pointer received: '+event.clientX+','+event.clientY});document.querySelector('#popup').addEventListener('click',()=>window.open('about:blank','qualification-popup','width=700,height=500'));</script></html>`;
const popupHTML = `<!doctype html><html lang="en"><meta charset="utf-8"><title>Qualification popup</title><style>body{font:18px system-ui;margin:35px;color:#172033;background:#eef7f4}button,input{font:inherit;padding:10px;margin:10px 0}output{display:block}</style><h1>Independent popup</h1><label for="value">Popup value</label><br><input id="value"><button>Apply popup value</button><output role="status">Waiting</output><script>document.querySelector('button').addEventListener('click',()=>{document.querySelector('output').textContent=document.querySelector('input').value});</script></html>`;

async function main() {
  const { values } = parseArgs({ options: {
    output: { type: 'string' }, project: { type: 'string' }, playwright: { type: 'string' },
    presentation: { type: 'string', default: 'headless' }, browser: { type: 'string', default: 'chromium' },
    provider: { type: 'string' }, width: { type: 'string', default: '1280' }, height: { type: 'string', default: '800' },
    'timeout-ms': { type: 'string', default: '60000' }, help: { type: 'boolean' },
  } });
  if (values.help) { console.log(help); return; }
  if (!values.output) throw new Error('--output requires a new evidence directory.');
  const width = positive(values.width, '--width'), height = positive(values.height, '--height');
  const timeout = positive(values['timeout-ms'], '--timeout-ms');
  const { openSession, createEvidenceRun, capture, observeContext, renderGallery } = await import('../runtime/index.mjs');
  const outputDir = resolve(values.output);
  const controller = new AbortController();
  const cancel = () => controller.abort(new Error('Qualification interrupted.'));
  process.once('SIGINT', cancel);
  process.once('SIGTERM', cancel);
  const timer = setTimeout(() => controller.abort(new Error('Qualification deadline reached.')), timeout);
  const checks = [], nativeFollowup = [];
  let run, session, diagnostics, failure, info;
  try {
    run = await createEvidenceRun({ outputDir, metadata: { purpose: 'Synthetic native session qualification', requested: { presentation: values.presentation, browser: values.browser, viewport: { width, height } } } });
    session = await openSession({
      projectDir: values.project ? resolve(values.project) : process.cwd(), playwrightPath: values.playwright,
      presentation: values.presentation, browser: values.browser, provider: values.provider,
      viewport: { width, height }, artifactDir: join(outputDir, '.execution'), signal: controller.signal,
    });
    info = session.info;
    const { browser, page, context } = session;
    page.setDefaultTimeout(Math.min(timeout, 15000));
    diagnostics = observeContext(context);
    await page.setContent(mainHTML, { waitUntil: 'domcontentloaded' });
    await page.getByLabel('Your message').focus();
    await page.keyboard.type('Keyboard input reached the owned page.');
    await page.keyboard.press('Enter');
    await page.getByRole('status').filter({ hasText: 'Keyboard input reached the owned page.' }).waitFor();
    checks.push({ property: 'keyboard input produces the expected page result', status: 'passed' });

    const button = page.getByRole('button', { name: 'Check pointer', exact: true });
    await button.scrollIntoViewIfNeeded();
    const bounds = await button.boundingBox();
    assert.ok(bounds, 'Pointer target has a visible bounding box.');
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.locator('#pointer-status').filter({ hasText: 'Pointer received:' }).waitFor();
    checks.push({ property: 'pointer input produces the expected page result', status: 'passed' });

    const [popup] = await Promise.all([
      page.waitForEvent('popup'),
      page.getByRole('button', { name: 'Open popup', exact: true }).click(),
    ]);
    popup.setDefaultTimeout(Math.min(timeout, 15000));
    await popup.setContent(popupHTML, { waitUntil: 'domcontentloaded' });
    await popup.getByLabel('Popup value').fill('Popup interaction succeeded.');
    await popup.getByRole('button', { name: 'Apply popup value' }).click();
    await popup.getByRole('status').filter({ hasText: 'Popup interaction succeeded.' }).waitFor();
    assert.ok(context.pages().includes(popup), 'Popup belongs to the owned browser context.');
    checks.push({ property: 'popup belongs to the session and accepts input', status: 'passed' });

    for (const [label, target] of [['Main page', page], ['Popup', popup]]) {
      const observation = await capture(target, { run, label, environment: info, state: { comparisonKey: label }, diagnostics, signal: controller.signal });
      assert.equal(observation.status, 'complete', `${label} capture completed: ${JSON.stringify(observation.warnings)}`);
      assert.ok(observation.images.length, `${label} capture contains an image.`);
      checks.push({ property: `${label} screenshot is stored`, status: 'passed', observationId: observation.id });
    }
    const geometry = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, scale: devicePixelRatio, screen: { width: screen.width, height: screen.height } }));
    assert.deepEqual({ width: geometry.width, height: geometry.height }, { width, height });
    checks.push({ property: 'observed viewport matches requested dimensions', status: 'passed', observed: geometry });
    await run.record({ type: 'environment', environment: info, observed: geometry });
    assert.equal(browser.isConnected(), true);
    if (values.presentation === 'isolated-headed') nativeFollowup.push('Verify the user’s foreground desktop stayed unchanged and native page/popup windows belong to the intended isolated display or desktop.');
    if (info.backend === 'configured-provider') nativeFollowup.push('Verify provider session teardown and expiry after owner loss on the actual rendering host.');
  } catch (error) {
    failure = error;
    if (run) await run.record({ type: 'qualification-error', message: error.message }).catch(() => {});
  } finally {
    clearTimeout(timer);
    diagnostics?.close();
    if (session) {
      try {
        const resourceDirectory = session.info.resourceDirectory;
        const temporaryDirectory = session.info.temporaryDirectory;
        await session.close();
        assert.equal(session.browser.isConnected(), false, 'Browser connection is closed.');
        checks.push({ property: 'owned browser connection is closed', status: 'passed' });
        if (session.info.diagnosticPath) {
          const receipt = JSON.parse(await readFile(session.info.diagnosticPath, 'utf8'));
          assert.equal(receipt.cleanup.status, 'completed', 'Retained session receipt records completed cleanup.');
          const artifact = await run.storeArtifact(session.info.diagnosticPath, { mime: 'application/json' });
          checks.push({ property: 'retained session receipt records completed cleanup', status: 'passed', artifact });
        }
        if (resourceDirectory) {
          let remains = false;
          try { await stat(resourceDirectory); remains = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
          assert.equal(remains, false, 'Owned execution resource directory is removed.');
          checks.push({ property: 'owned execution resource directory is removed', status: 'passed' });
        }
        if (temporaryDirectory) {
          let remains = false;
          try { await stat(temporaryDirectory); remains = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
          assert.equal(remains, false, 'Owned browser temporary directory is removed.');
          checks.push({ property: 'owned browser temporary directory is removed', status: 'passed' });
        }
      } catch (error) {
        failure ??= error;
        checks.push({ property: 'owned cleanup', status: 'failed', message: error.message });
      }
    }
    process.removeListener('SIGINT', cancel);
    process.removeListener('SIGTERM', cancel);
    if (run) {
      try {
        await run.record({ type: 'qualification', status: failure ? 'failed' : 'passed', checks, nativeFollowup, environment: info, error: failure?.message });
        await run.finish();
      } finally { await run.close(); }
      const gallery = await renderGallery(outputDir);
      console.log(JSON.stringify({ status: failure ? 'failed' : 'passed', checks: checks.length, outputDir, index: gallery.indexPath, nativeFollowup }));
    }
  }
  if (failure) throw failure;
}

main().catch(error => {
  console.error(`error: ${error.message}`);
  if (error.hint) console.error(`hint: ${error.hint}`);
  process.exitCode = 1;
});
