import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createHash, randomUUID } from 'node:crypto';
import { mkdtemp, mkdir, writeFile, readFile, readdir, stat, symlink, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { acquireEvidenceLock, createEvidenceRun, importCaptureCollection, compareRuns, readEvidenceRun } from '../../../plugins/playwright-testing/runtime/evidence.mjs';
import { renderGallery } from '../../../plugins/playwright-testing/runtime/gallery.mjs';

async function fixture(t) {
  const parent = process.env.PW_TEST_EVIDENCE_FS_OUTPUT || os.tmpdir();
  await mkdir(parent, { recursive: true });
  const root = await mkdtemp(path.join(parent, 'evidence-followup-'));
  if (!process.env.PW_TEST_EVIDENCE_FS_OUTPUT) t.after(() => rm(root, { recursive: true, force: true }));
  return root;
}
const alias = (source, output) => symlink(source, output, process.platform === 'win32' ? 'junction' : 'dir');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

test('aliased import destination is refused before any source mutation', async t => {
  const root = await fixture(t), source = path.join(root, 'source');
  await mkdir(source); await writeFile(path.join(source, 'summary.json'), '{"captures":[],"context":"preserved"}');
  await alias(source, path.join(root, 'first-alias')); await alias(path.join(root, 'first-alias'), path.join(root, 'second-alias'));
  const before = await readdir(source), summary = await readFile(path.join(source, 'summary.json'));
  for (const aliased of ['first-alias', 'second-alias']) await assert.rejects(importCaptureCollection(source, { outputDir: path.join(root, aliased, 'missing parent', 'output') }), /separate directory outside the source/);
  assert.deepEqual(await readdir(source), before); assert.deepEqual(await readFile(path.join(source, 'summary.json')), summary);
  await assert.rejects(stat(path.join(source, 'missing parent')), { code: 'ENOENT' });
  t.diagnostic(JSON.stringify({ root, sourceFiles: await readdir(source), sourceUnchanged: true }));
});

test('aliased comparison output is refused inside either source before mutation', async t => {
  const root = await fixture(t);
  for (const name of ['left', 'right']) {
    const run = await createEvidenceRun({ outputDir: path.join(root, name) });
    await run.record({ type: 'capture', id: name, state: { url: 'https://fixture.invalid/#same-state' }, images: [] }); await run.close();
    await alias(run.outputDir, path.join(root, `${name}-alias`));
  }
  for (const name of ['left', 'right']) {
    const source = path.join(root, name), before = await readdir(source), journal = await readFile(path.join(source, 'observations.ndjson'));
    await assert.rejects(compareRuns(path.join(root, 'left'), path.join(root, 'right'), { outputDir: path.join(root, `${name}-alias`, 'not created', 'comparison') }), /separate directory outside both source/);
    assert.deepEqual(await readdir(source), before); assert.deepEqual(await readFile(path.join(source, 'observations.ndjson')), journal);
    await assert.rejects(stat(path.join(source, 'not created')), { code: 'ENOENT' });
  }
  t.diagnostic(JSON.stringify({ root, bothSourcesUnchanged: true }));
});

test('a separate aliased output parent remains usable and resolves to its actual destination', async t => {
  const root = await fixture(t), source = path.join(root, 'source'), destination = path.join(root, 'separate output ü');
  await mkdir(source); await writeFile(path.join(source, 'summary.json'), '{"captures":[]}'); await mkdir(destination);
  await alias(destination, path.join(root, 'safe-alias'));
  const imported = await importCaptureCollection(source, { outputDir: path.join(root, 'safe-alias', 'new', 'run') });
  assert.equal(imported.outputDir, path.join(destination, 'new', 'run'));
  assert.ok(await stat(path.join(imported.outputDir, 'run.json')));
  assert.deepEqual(await readdir(source), ['summary.json']);
});

test('killed gallery writer is recovered while its last accepted gallery stays available', { timeout: 30000 }, async t => {
  const root = await fixture(t), run = await createEvidenceRun({ outputDir: path.join(root, 'run') });
  for (let i = 0; i < 700; i++) await run.record({ id: `state-${i}`, type: 'capture', label: `State ${i}`, state: { url: `https://fixture.invalid/?state=${i}#view` }, context: 'Retained source context '.repeat(20) });
  await run.finish(); await run.close();
  const accepted = await renderGallery(run.outputDir), acceptedHash = sha(await readFile(accepted.indexPath));
  const resumed = await createEvidenceRun({ outputDir: run.outputDir, resume: true });
  await resumed.record({ id: 'new-state', type: 'capture', label: 'New state' }); await resumed.close();
  const moduleUrl = new URL('../../../plugins/playwright-testing/runtime/gallery.mjs', import.meta.url).href;
  const child = spawn(process.execPath, ['--input-type=module', '-e', `import {renderGallery} from ${JSON.stringify(moduleUrl)}; await renderGallery(${JSON.stringify(run.outputDir)});`], { stdio: ['ignore', 'ignore', 'pipe'] });
  let errors = ''; child.stderr.on('data', bytes => { errors += bytes; });
  t.after(() => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); });
  let stage;
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    stage = (await readdir(run.outputDir)).find(name => /^\.gallery-[a-f0-9-]{36}$/.test(name));
    if (stage) {
      const files = await readdir(path.join(run.outputDir, stage, 'records')).catch(() => []);
      if (files.length >= 5) break;
    }
    if (child.exitCode !== null || child.signalCode !== null) throw new Error(`Gallery exited before interruption: ${errors}`);
    await new Promise(resolve => setTimeout(resolve, 5)); stage = undefined;
  }
  assert.ok(stage, 'Observed incremental gallery build before interruption');
  const owner = JSON.parse(await readFile(path.join(run.outputDir, '.gallery-lock', 'owner.json'), 'utf8'));
  assert.equal(owner.pid, child.pid);
  const exited = once(child, 'exit'); child.kill('SIGKILL'); await exited;
  assert.equal(sha(await readFile(accepted.indexPath)), acceptedHash, 'Last accepted gallery remains available during interruption');
  const recovered = await renderGallery(run.outputDir);
  assert.equal(recovered.observations, 701); assert.ok(await stat(recovered.indexPath));
  assert.equal((await readEvidenceRun(run.outputDir, { includeRecords: false })).summary.observations, 701);
  assert.ok(!(await readdir(run.outputDir)).some(name => name === '.gallery-lock' || name === stage));
  t.diagnostic(JSON.stringify({ root, interruptedStage: stage, recoveredObservations: recovered.observations, acceptedGalleryPreservedDuringInterruption: true }));
});

test('gallery recovery leaves live and foreign lock ownership intact', async t => {
  const root = await fixture(t), run = await createEvidenceRun({ outputDir: path.join(root, 'run') }); await run.close();
  const accepted = await renderGallery(run.outputDir), before = await readFile(accepted.indexPath);
  const release = await acquireEvidenceLock(run.outputDir, '.gallery-lock');
  await assert.rejects(renderGallery(run.outputDir), /owned by another writer/);
  await release();
  const lock = path.join(run.outputDir, '.gallery-lock'); await mkdir(lock);
  const foreignOwner = JSON.stringify({ host: 'different-host.invalid', pid: 999999999, token: randomUUID() });
  await writeFile(path.join(lock, 'owner.json'), foreignOwner);
  await assert.rejects(renderGallery(run.outputDir), /owned by another writer/);
  assert.equal(await readFile(path.join(lock, 'owner.json'), 'utf8'), foreignOwner); assert.deepEqual(await readFile(accepted.indexPath), before);
});
