import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import { importCaptureCollection, readEvidenceRun, resolveEvidenceFile } from '../../../plugins/playwright-testing/runtime/evidence.mjs';
import { renderGallery } from '../../../plugins/playwright-testing/runtime/gallery.mjs';

const source = process.env.PW_TEST_CAPTURE_COLLECTION;
test('actual supplied capture collection imports every observation and preserves exact-byte deduplication', { skip: !source, timeout: 120000 }, async t => {
  const output = process.env.PW_TEST_EVIDENCE_OUTPUT || await mkdtemp(path.join(os.tmpdir(), 'pw-corpus-'));
  if (!process.env.PW_TEST_EVIDENCE_OUTPUT) t.after(() => rm(output, { recursive: true, force: true }));
  const original = JSON.parse(await readFile(path.join(source, 'summary.json'), 'utf8'));
  const hashes = new Set(); let images = 0;
  for (const record of original.captures) for (const image of record.images) {
    const file = await resolveEvidenceFile(source, typeof image === 'string' ? image : image.file);
    const hash = createHash('sha256');
    for await (const bytes of createReadStream(file)) hash.update(bytes);
    hashes.add(hash.digest('hex')); images += 1;
  }
  const imported = await importCaptureCollection(source, { outputDir: output, resume: process.env.PW_TEST_EVIDENCE_RESUME === '1', signal: t.signal });
  assert.equal(imported.summary.imageReferences, images); assert.equal(imported.summary.uniqueImages, hashes.size); assert.equal(imported.summary.captures, original.captures.length);
  const read = await readEvidenceRun(output, { type: 'capture', limit: Infinity });
  assert.deepEqual(read.records.map(record => record.sourceCapture), original.captures);
  let stored = 0;
  for (const prefix of await readdir(path.join(output, 'blobs'))) for (const hash of await readdir(path.join(output, 'blobs', prefix))) if (hashes.has(hash)) stored += 1;
  assert.equal(stored, hashes.size);
  const gallery = await renderGallery(output);
  t.diagnostic(JSON.stringify({ sourceCaptures: original.captures.length, sourceImages: images, uniqueImages: hashes.size, duplicates: images - hashes.size, storedImageBytes: imported.summary.storedImageBytes, gallery: gallery.indexPath }));
});
