import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { inflateRawSync } from 'node:zlib';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { openSession } from '../../../plugins/playwright-testing/runtime/session.mjs';
import { createEvidenceRun, readEvidenceRun } from '../../../plugins/playwright-testing/runtime/evidence.mjs';
import { capture } from '../../../plugins/playwright-testing/runtime/capture.mjs';
import { observeContext } from '../../../plugins/playwright-testing/runtime/discovery.mjs';
import { serveSurveyFixture } from './fixtures/browser-survey/server.mjs';

const execute = promisify(execFile);

// A bounded ZIP reader for inspecting the ordinary trace ZIP produced by this test.
function readZip(bytes) {
  const end = bytes.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  assert.ok(end >= 0, 'Trace has a ZIP end-of-directory record');
  let offset = bytes.readUInt32LE(end + 16);
  const entries = new Map();
  const count = bytes.readUInt16LE(end + 10);
  assert.ok(count > 0 && count < 1000, 'Synthetic trace has a bounded nonempty directory');
  for (let index = 0; index < count; index++) {
    assert.equal(bytes.readUInt32LE(offset), 0x02014b50);
    const method = bytes.readUInt16LE(offset + 10), size = bytes.readUInt32LE(offset + 20);
    const nameLength = bytes.readUInt16LE(offset + 28), extraLength = bytes.readUInt16LE(offset + 30), commentLength = bytes.readUInt16LE(offset + 32);
    const name = bytes.toString('utf8', offset + 46, offset + 46 + nameLength);
    const local = bytes.readUInt32LE(offset + 42);
    assert.equal(bytes.readUInt32LE(local), 0x04034b50);
    const dataStart = local + 30 + bytes.readUInt16LE(local + 26) + bytes.readUInt16LE(local + 28);
    const compressed = bytes.subarray(dataStart, dataStart + size);
    const data = method === 0 ? compressed : method === 8 ? inflateRawSync(compressed, { maxOutputLength: 20 * 1024 * 1024 }) : null;
    assert.ok(data, `Trace entry uses a supported ZIP compression method: ${name}`);
    entries.set(name, data);
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

test('native session retains usable trace and video evidence through partial capture and teardown', { skip: !process.env.PW_TEST_PLAYWRIGHT_PATH, timeout: 90000 }, async t => {
  const output = await mkdtemp(path.join(process.env.PW_CAPTURE_TEST_OUTPUT || tmpdir(), 'capture-artifacts-'));
  const producer = path.join(output, 'producer'), resources = path.join(output, 'resources'), runDir = path.join(output, 'evidence');
  await mkdir(producer);
  const fixture = await serveSurveyFixture();
  const run = await createEvidenceRun({ outputDir: runDir, metadata: { purpose: 'Native trace/video retention across success and a synthetic missing-target failure' } });
  let session, observer, tracing = false;
  t.after(async () => { observer?.close(); await session?.close(); await run.close(); await fixture.close(); if (!process.env.PW_CAPTURE_TEST_OUTPUT) await rm(output, { recursive: true, force: true }); });
  try {
    session = await openSession({
      playwrightPath: process.env.PW_TEST_PLAYWRIGHT_PATH, resourceRoot: resources,
      viewport: { width: 640, height: 480 }, contextOptions: { recordVideo: { dir: producer, size: { width: 320, height: 240 } } },
    });
  } catch (error) {
    throw new Error(`Native video session setup failed: ${error.message}\nUse the matching Playwright installation's browser installer to supply its browser and ffmpeg artifacts.`, { cause: error });
  }
  const { page, context, browser } = session;
  const video = page.video();
  assert.ok(video, 'recordVideo supplies a video handle');
  observer = observeContext(context);
  await run.record({ type: 'session', info: session.info });
  await context.tracing.start({ screenshots: true, snapshots: true });
  tracing = true;
  const tracePath = path.join(producer, 'journey.zip'), videoPath = path.join(producer, 'journey.webm');
  let complete, partial;
  try {
    await page.goto(fixture.url, { waitUntil: 'domcontentloaded' });
    await page.getByRole('tab', { name: 'Details', exact: true }).click();
    await page.getByRole('button', { name: 'Review note', exact: true }).click();
    await page.getByRole('textbox', { name: 'Note', exact: true }).fill('Synthetic review text retained in trace and video.');
    await page.getByRole('button', { name: 'Save note', exact: true }).click();
    await page.getByRole('button', { name: 'Close review', exact: true }).click();
    assert.equal(await page.evaluate(() => localStorage.getItem('survey-note')), 'Synthetic review text retained in trace and video.');
    complete = await capture(page, { run, label: 'Synthetic note saved', state: { actions: ['Open Details', 'Create synthetic note', 'Close review'] }, diagnostics: observer });
    assert.equal(complete.status, 'complete');
    partial = await capture(page, { run, label: 'Expected missing-target observation', target: '#synthetic-absent-target', timeout: 350, diagnostics: observer });
    assert.equal(partial.status, 'partial');
    assert.equal(partial.images.length, 0);
    assert.ok(partial.warnings.some(warning => warning.message.includes('synthetic-absent-target')));
  } finally {
    // Stop tracing while its context exists, including when the journey throws.
    if (tracing) { await context.tracing.stop({ path: tracePath }); tracing = false; }
  }
  const trace = await run.storeArtifact(tracePath, { extension: 'zip', mime: 'application/zip' });
  await run.record({ type: 'trace', label: 'Synthetic journey and expected capture timeout', relatedCaptures: [complete.id, partial.id], artifact: trace });
  await context.close();
  assert.equal(browser.isConnected(), true, 'Context teardown leaves the transfer connection alive');
  // saveAs works over the session's Playwright connection; path() is local-only.
  await video.saveAs(videoPath);
  const recording = await run.storeArtifact(videoPath, { extension: 'webm', mime: 'video/webm' });
  await run.record({ type: 'video', label: 'Synthetic note journey', relatedCaptures: [complete.id, partial.id], artifact: recording });
  observer.close();
  await session.close();
  assert.equal(browser.isConnected(), false);
  assert.deepEqual(await readdir(resources), []);
  await rm(producer, { recursive: true });
  await run.finish();
  await run.close();

  const retained = await readEvidenceRun(runDir, { limit: Infinity });
  assert.equal(retained.summary.partialCaptures, 1);
  assert.equal(retained.summary.imageReferences, 1);
  const traceRecord = retained.records.find(record => record.type === 'trace');
  const videoRecord = retained.records.find(record => record.type === 'video');
  assert.deepEqual(traceRecord.relatedCaptures, [complete.id, partial.id]);
  assert.deepEqual(videoRecord.relatedCaptures, [complete.id, partial.id]);
  const traceBytes = await readFile(path.join(runDir, traceRecord.artifact.path));
  const videoBytes = await readFile(path.join(runDir, videoRecord.artifact.path));
  for (const [bytes, ref] of [[traceBytes, trace], [videoBytes, recording]]) {
    assert.equal(createHash('sha256').update(bytes).digest('hex'), ref.sha256);
    assert.equal(bytes.length, ref.size);
  }
  const traceEntries = readZip(traceBytes);
  const traceLog = [...traceEntries].filter(([name]) => name.endsWith('.trace')).flatMap(([, bytes]) => bytes.toString('utf8').trim().split('\n').map(line => JSON.parse(line)));
  assert.ok(traceLog.some(event => event.type === 'before' && event.method === 'click'), 'Trace retains real Playwright click calls');
  assert.ok(traceLog.some(event => event.type === 'after' && event.error), 'Trace retains the actual missing-target timeout');
  assert.ok([...traceEntries.values()].some(bytes => bytes.subarray(0, 3).equals(Buffer.from([0xff, 0xd8, 0xff])) || bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))), 'Trace contains native screenshot bytes');
  assert.ok([...traceEntries].some(([name, bytes]) => name.endsWith('.network') && bytes.includes(Buffer.from(fixture.url))), 'Trace contains the actual synthetic HTTP route');
  assert.equal(videoBytes.readUInt32BE(0), 0x1a45dfa3, 'Recorded video has a WebM EBML header');
  let probe;
  try {
    // A configured decoder may own another /tmp namespace. Stream the exact
    // retained bytes through its normal input interface instead of sharing paths.
    const decoding = execute('ffprobe', ['-v', 'error', '-count_frames', '-show_entries', 'stream=codec_type,width,height,nb_read_frames', '-of', 'json', '-i', 'pipe:0'], { timeout: 10000, maxBuffer: 1024 * 1024 });
    let inputError;
    decoding.child.stdin.on('error', error => { inputError = error; });
    decoding.child.stdin.end(videoBytes);
    const { stdout } = await decoding;
    if (inputError) throw inputError;
    probe = JSON.parse(stdout);
    const stream = probe.streams.find(stream => stream.codec_type === 'video');
    assert.equal(stream.width, 320); assert.equal(stream.height, 240);
    assert.ok(Number(stream.nb_read_frames) >= 2, 'The saved video has multiple decodable frames');
    t.diagnostic(`Native ffprobe decoded ${stream.nb_read_frames} frames at ${stream.width}×${stream.height} from retained bytes via stdin.`);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    probe = { limitation: 'ffprobe is unavailable; WebM identity and retention were checked, native decoding remains unqualified.' };
    t.diagnostic(probe.limitation);
  }
  await writeFile(path.join(output, 'artifact-validation.json'), JSON.stringify({ traceEntries: [...traceEntries.keys()], trace, recording, videoProbe: probe, observations: retained.summary }, null, 2));
  t.diagnostic(`Trace/video evidence survives producer and session teardown: ${output}`);
});
