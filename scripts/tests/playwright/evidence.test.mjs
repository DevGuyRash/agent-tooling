import test from 'node:test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, readdir, appendFile, symlink, mkdir, stat, rm, rename } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { createEvidenceRun, readEvidenceRun, importCaptureCollection, compareRuns } from '../../../plugins/playwright-testing/runtime/evidence.mjs';
import { renderGallery } from '../../../plugins/playwright-testing/runtime/gallery.mjs';

const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6FhEAAAAASUVORK5CYII=', 'base64');
async function fixture(t) { const root = await mkdtemp(path.join(os.tmpdir(), 'pw evidence ü ')); t.after(() => rm(root, { recursive: true, force: true })); return root; }
async function newRun(root, name = 'run', metadata = {}) { return createEvidenceRun({ outputDir: path.join(root, name), metadata }); }

test('stores original bytes once while preserving identities, state, and arbitrary context', async t => {
  const root = await fixture(t), run = await newRun(root);
  const [a, b] = await Promise.all([run.storeBlob(image, { extension: 'png' }), run.storeBlob(image, { extension: 'webp', mime: 'image/webp' })]);
  assert.equal(a.path, b.path);
  assert.deepEqual(await readFile(path.join(run.outputDir, a.path)), image);
  assert.equal(a.sha256, createHash('sha256').update(image).digest('hex'));
  await Promise.all(['a', 'b'].map(id => run.record({ id, type: 'capture', label: 'Repeated', state: { url: `https://example.org/?x=${id}#view` }, images: [a], extra: { why: ['full context', '🦄'] } })));
  await run.enqueue({ id: 'future', arbitrary: { journey: [1, 2] } });
  assert.equal((await run.pendingTasks()).length, 1);
  await run.finish(); await run.close();
  const read = await readEvidenceRun(run.outputDir, { query: 'context', limit: 1 });
  assert.equal(read.summary.imageReferences, 2); assert.equal(read.summary.uniqueImages, 1); assert.equal(read.summary.duplicateImages, 1);
  assert.equal(read.summary.matching, 2); assert.equal(read.summary.hasMore, true);
  assert.equal(read.records[0].extra.why[1], '🦄');
  assert.deepEqual(read.pendingTasks[0].arbitrary.journey, [1, 2]);
});

test('resume retains work, recovers incomplete tail bytes, and detects concurrent writers', async t => {
  const root = await fixture(t), run = await newRun(root);
  await run.record({ id: 'original', type: 'observation' });
  await run.enqueue({ id: 'todo', state: { nested: true } });
  await assert.rejects(createEvidenceRun({ outputDir: run.outputDir, resume: true }), /owned by another writer/);
  await run.close();
  await appendFile(path.join(run.outputDir, 'observations.ndjson'), '{"version":1,"event":"observation","obser');
  const interrupted = await readEvidenceRun(run.outputDir); assert.ok(interrupted.summary.trailingBytes > 0);
  const resumed = await createEvidenceRun({ outputDir: run.outputDir, resume: true });
  assert.deepEqual((await resumed.pendingTasks())[0], { id: 'todo', state: { nested: true } });
  await resumed.enqueue({ id: 'todo', state: { nested: true } });
  await assert.rejects(resumed.enqueue({ id: 'todo', state: { nested: false } }), /different context/);
  await assert.rejects(resumed.record({ id: 'original' }), /already exists/);
  await resumed.complete('todo', { id: 'original' });
  await resumed.record({ id: 'second', meaning: 'after recovery' });
  await resumed.close();
  const read = await readEvidenceRun(run.outputDir);
  assert.equal(read.summary.observations, 2); assert.equal(read.summary.trailingBytes, 0); assert.equal(read.summary.pendingTasks, 0);
  const recovered = await readdir(path.join(run.outputDir, 'recovery')); assert.equal(recovered.length, 1);
  assert.match(await readFile(path.join(run.outputDir, 'recovery', recovered[0]), 'utf8'), /obser$/);
});

test('committed corruption is not silently discarded and completed runs reopen as unfinished when appended', async t => {
  const root = await fixture(t), run = await newRun(root);
  await run.record({ id: 'a' }); await run.finish(); await run.close();
  const resumed = await createEvidenceRun({ outputDir: run.outputDir, resume: true });
  await resumed.record({ id: 'b' }); await resumed.close();
  assert.equal((await readEvidenceRun(run.outputDir)).summary.finishedAt, null);
  await appendFile(path.join(run.outputDir, 'observations.ndjson'), '{broken}\n');
  await assert.rejects(createEvidenceRun({ outputDir: run.outputDir, resume: true }), /invalid committed record/);
  assert.equal((await readdir(run.outputDir)).includes('.writer-lock'), false);
});

test('mutable staging and journals cannot follow planted symlinks', async t => {
  const root = await fixture(t), run = await newRun(root);
  await run.close();
  const outside = path.join(root, 'outside'); await mkdir(outside); await writeFile(path.join(outside, 'keep'), 'valuable');
  await rm(path.join(run.outputDir, '.staging'), { recursive: true });
  await symlink(outside, path.join(run.outputDir, '.staging'));
  await assert.rejects(createEvidenceRun({ outputDir: run.outputDir, resume: true }), /owned and real/);
  assert.equal(await readFile(path.join(outside, 'keep'), 'utf8'), 'valuable');
});

test('legacy import streams exact bytes, preserves metadata, resumes, and rejects path escapes', async t => {
  const root = await fixture(t), source = path.join(root, 'source'); await mkdir(path.join(source, 'images'), { recursive: true });
  await writeFile(path.join(source, 'images', 'a.png'), image); await writeFile(path.join(source, 'images', 'b.png'), image);
  const summary = { arbitrary: { important: ['source'] }, options: { height: 800 }, captures: [{ report: 'a.html', width: 390, scheme: 'dark', hash: '#one', view: '</script><img onerror="bad()">', images: [{ file: 'images/a.png', scrollY: 0 }, { file: 'images/b.png', scrollY: 500 }], qualification: 'kept' }] };
  const raw = JSON.stringify(summary, null, 3); await writeFile(path.join(source, 'summary.json'), raw);
  const imported = await importCaptureCollection(source, { outputDir: path.join(root, 'imported') });
  assert.equal(imported.summary.imageReferences, 2); assert.equal(imported.summary.uniqueImages, 1);
  const read = await readEvidenceRun(imported.outputDir, { type: 'capture' });
  assert.equal(read.records[0].sourceCapture.qualification, 'kept'); assert.equal(read.records[0].images[1].scrollY, 500);
  const originals = await readEvidenceRun(imported.outputDir, { type: 'import-source' });
  assert.equal(await readFile(path.join(imported.outputDir, originals.records[0].source.metadata.path), 'utf8'), raw);
  const resumed = await importCaptureCollection(source, { outputDir: imported.outputDir, resume: true });
  assert.equal(resumed.imported, 0); assert.equal(resumed.summary.imageReferences, 2);
  const gallery = await renderGallery(imported.outputDir);
  const generated = await readFile(path.join(path.dirname(gallery.indexPath), 'records', '000002.html'), 'utf8');
  assert.ok(generated.includes('&lt;/script&gt;')); assert.ok(!generated.includes('<img onerror='));
  const data = await readFile(path.join(path.dirname(gallery.indexPath), 'gallery-data.js'), 'utf8'); assert.ok(!data.includes('</script>'));
  summary.captures[0].images = [{ file: '../secret.png' }]; await writeFile(path.join(source, 'summary.json'), JSON.stringify(summary)); await writeFile(path.join(root, 'secret.png'), image);
  await assert.rejects(importCaptureCollection(source, { outputDir: path.join(root, 'escaped') }), /contained relative/);
});

test('native imports preserve arbitrary artifact trees, pending work, and observed relationships', async t => {
  const root = await fixture(t), source = await newRun(root, 'source');
  const blob = await source.storeBlob(image, { extension: 'png' });
  const trace = await source.storeBlob(Buffer.from('trace'), { extension: 'zip' });
  await source.record({ id: 'capture-a', type: 'capture', images: [blob], state: { url: 'https://site/a' }, custom: { trace } });
  await source.record({ id: 'edge', type: 'transition', from: 'capture-a', to: 'capture-a', action: 'Refresh' });
  await source.enqueue({ id: 'todo', precise: 'context' }); await source.close();
  const imported = await importCaptureCollection(source.outputDir, { outputDir: path.join(root, 'imported') });
  const read = await readEvidenceRun(imported.outputDir, { limit: Infinity });
  const capture = read.records.find(record => record.type === 'capture');
  assert.deepEqual(await readFile(path.join(imported.outputDir, capture.custom.trace.path)), Buffer.from('trace'));
  assert.equal(read.records.find(record => record.type === 'transition').from, capture.id);
  assert.equal(read.pendingTasks[0].precise, 'context');
});

test('progress remains recoverable without duplicating completed capture images', async t => {
  const root = await fixture(t), run = await newRun(root);
  const blob = await run.storeBlob(image, { extension: 'png' });
  await run.record({ type: 'capture-progress', captureId: 'finished', images: [blob] });
  await run.record({ type: 'capture', id: 'finished', images: [blob] });
  await run.record({ type: 'capture-progress', captureId: 'interrupted', images: [blob] });
  await run.close();
  const summary = (await readEvidenceRun(run.outputDir)).summary;
  assert.equal(summary.imageReferences, 2); assert.equal(summary.incompleteCaptures, 1);
  const gallery = await renderGallery(run.outputDir);
  assert.equal(gallery.images, 2); assert.equal(gallery.hiddenProgress, 1);
  assert.equal((await renderGallery(run.outputDir)).observations, 2);
});

test('comparison preserves duplicate ambiguity and complete left/right originals', async t => {
  const root = await fixture(t);
  for (const side of ['left', 'right']) {
    const run = await newRun(root, side), blob = await run.storeBlob(image, { extension: 'png' });
    await run.record({ id: `${side}-one`, type: 'capture', label: 'One', state: { url: 'https://site/?one#full' }, images: [blob] });
    await run.record({ id: `${side}-two`, type: 'capture', label: 'Repeated', state: { comparisonKey: 'ambiguous' }, images: [blob] });
    if (side === 'left') await run.record({ id: 'left-duplicate', type: 'capture', label: 'Repeated', state: { comparisonKey: 'ambiguous' }, images: [blob] });
    await run.record({ id: `${side}-unique`, type: 'capture', state: { url: `https://site/${side}` }, images: [blob] });
    await run.close();
  }
  const compared = await compareRuns(path.join(root, 'left'), path.join(root, 'right'), { outputDir: path.join(root, 'comparison') });
  assert.deepEqual(compared.summary, { matched: 1, identical: 1, different: 0, noImages: 0, ambiguous: 1, onlyLeft: 1, onlyRight: 1 });
  assert.equal(compared.ambiguous[0].left.length, 2);
  const records = await readEvidenceRun(compared.outputDir);
  assert.equal(records.summary.imageReferences, 7); assert.equal(records.summary.uniqueImages, 1);
  assert.ok(records.records.some(record => record.images.some(ref => ref.side === 'right')));
  assert.ok(await stat((await renderGallery(compared.outputDir)).indexPath));
});

test('in-run byte tampering is rejected and partial final captures remain counted', async t => {
  const root = await fixture(t), run = await newRun(root);
  const blob = await run.storeBlob(image, { extension: 'png' });
  await writeFile(path.join(run.outputDir, blob.path), Buffer.alloc(image.length));
  await assert.rejects(run.storeBlob(image, { extension: 'png' }), /Stored artifact is damaged/);
  await writeFile(path.join(run.outputDir, blob.path), image);
  await run.record({ id: 'partial', type: 'capture', status: 'partial', images: [blob] });
  await run.record({ id: 'failed', type: 'capture', status: 'failed', images: [] });
  await run.record({ id: 'cancelled', type: 'capture', status: 'cancelled', images: [] });
  await run.close();
  const read = await readEvidenceRun(run.outputDir);
  assert.equal(read.summary.partialCaptures, 1); assert.equal(read.summary.failedCaptures, 1); assert.equal(read.summary.cancelledCaptures, 1);
});

test('gallery and comparisons detect changed evidence bytes without changing the source', async t => {
  const root = await fixture(t);
  const a = await newRun(root, 'a'), b = await newRun(root, 'b');
  const ref = await a.storeBlob(image, { extension: 'png' }), other = await b.storeBlob(image, { extension: 'png' });
  await a.record({ type: 'capture', state: { url: 'https://site' }, images: [ref] }); await a.close();
  await b.record({ type: 'capture', state: { url: 'https://site' }, images: [other] }); await b.close();
  await writeFile(path.join(a.outputDir, ref.path), Buffer.alloc(image.length));
  await assert.rejects(renderGallery(a.outputDir), /bytes differ/);
  await assert.rejects(compareRuns(a.outputDir, b.outputDir), /bytes differ/);
  assert.deepEqual(await readFile(path.join(a.outputDir, ref.path)), Buffer.alloc(image.length));
});


test('process interruption leaves completed bytes and pending tasks recoverable', { timeout: 10000 }, async t => {
  const root = await fixture(t), outputDir = path.join(root, 'killed');
  const moduleUrl = new URL('../../../plugins/playwright-testing/runtime/evidence.mjs', import.meta.url).href;
  const code = `import {createEvidenceRun} from ${JSON.stringify(moduleUrl)}; const run=await createEvidenceRun({outputDir:${JSON.stringify(outputDir)}}); const blob=await run.storeBlob(Buffer.from('accepted-before-interruption'),{extension:'txt'}); await run.record({id:'accepted',artifact:blob}); await run.enqueue({id:'pending',context:{after:'accepted'}}); process.stdout.write('ready\\n'); setInterval(()=>{},1000);`;
  const child = spawn(process.execPath, ['--input-type=module', '-e', code], { stdio: ['ignore', 'pipe', 'pipe'] });
  let errors = ''; child.stderr.on('data', bytes => { errors += bytes; });
  t.after(() => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); });
  await Promise.race([once(child.stdout, 'data'), once(child, 'exit').then(() => { throw new Error(`Writer exited before ready: ${errors}`); })]);
  const exited = once(child, 'exit'); child.kill('SIGKILL'); await exited;
  const resumed = await createEvidenceRun({ outputDir, resume: true });
  const read = await readEvidenceRun(outputDir);
  assert.equal(await readFile(path.join(outputDir, read.records[0].artifact.path), 'utf8'), 'accepted-before-interruption');
  assert.deepEqual(await resumed.pendingTasks(), [{ id: 'pending', context: { after: 'accepted' } }]);
  await resumed.complete('pending', { recovered: true }); await resumed.finish(); await resumed.close();
  assert.equal((await readEvidenceRun(outputDir)).summary.pendingTasks, 0);
});

test('disk flushing mode persists its contract and rejects conflicting resumption', async t => {
  const root = await fixture(t), outputDir = path.join(root, 'disk');
  const run = await createEvidenceRun({ outputDir, durability: 'disk' });
  await run.storeBlob(image, { extension: 'png' }); await run.record({ id: 'durable' }); await run.close();
  assert.equal((await readEvidenceRun(outputDir)).run.durability, 'disk');
  await assert.rejects(createEvidenceRun({ outputDir, resume: true, durability: 'process' }), /durability differs/);
  const resumed = await createEvidenceRun({ outputDir, resume: true }); assert.equal(resumed.durability, 'disk'); await resumed.close();
});


test('gallery resumes an interrupted directory publication while preserving unrelated files', async t => {
  const root = await fixture(t), run = await newRun(root);
  const blob = await run.storeBlob(image, { extension: 'png' });
  await run.record({ type: 'capture', images: [blob] }); await run.close();
  const first = await renderGallery(run.outputDir);
  const backup = path.join(run.outputDir, `.gallery-previous-${randomUUID()}`);
  await rename(path.dirname(first.indexPath), backup);
  const abandoned = path.join(run.outputDir, `.gallery-${randomUUID()}`); await mkdir(abandoned);
  await writeFile(path.join(abandoned, 'owner.json'), JSON.stringify({ runId: run.id, generatedAt: '2026-09-24' }));
  const unrelated = path.join(run.outputDir, `.gallery-${randomUUID()}`); await mkdir(unrelated); await writeFile(path.join(unrelated, 'keep'), 'untouched');
  const recovered = await renderGallery(run.outputDir);
  assert.ok(await stat(recovered.indexPath));
  await assert.rejects(stat(backup), { code: 'ENOENT' }); await assert.rejects(stat(abandoned), { code: 'ENOENT' });
  assert.equal(await readFile(path.join(unrelated, 'keep'), 'utf8'), 'untouched');
});
