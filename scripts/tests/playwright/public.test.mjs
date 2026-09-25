import test from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, mkdir, rm } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';
import { createEvidenceRun, readEvidenceRun } from '../../../plugins/playwright-testing/runtime/evidence.mjs';
import { serveSurveyFixture } from './fixtures/browser-survey/server.mjs';

const exec = promisify(execFile);
const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const cli = join(repo, 'plugins/playwright-testing/scripts/browser-tools.mjs');
const artifacts = join(repo, '.local/context/playwright-survey-implementation/integration');
const playwrightPath = process.env.PW_TEST_PLAYWRIGHT_PATH;
const native = { skip: !playwrightPath && 'Set PW_TEST_PLAYWRIGHT_PATH for native public-interface checks.', timeout: 90000 };
await mkdir(artifacts, { recursive: true });
const workspace = await mkdtemp(join(artifacts, 'public-'));
await mkdir(join(workspace, 'other directory Ω'));
const cwd = join(workspace, 'other directory Ω');

async function command(args, options = {}) {
  try {
    const result = await exec(process.execPath, [cli, ...args], { cwd, timeout: 60000, maxBuffer: 4 * 1024 * 1024, ...options });
    return { code: 0, ...result };
  } catch (error) {
    if (typeof error.code !== 'number') throw error;
    return { code: error.code, stdout: error.stdout, stderr: error.stderr };
  }
}
const lastJSON = text => JSON.parse(text.trim().split('\n').at(-1));

test('CLI help and invalid commands work before runtime discovery', async () => {
  const help = await command(['--help']);
  assert.equal(help.code, 0);
  assert.match(help.stdout, /isolate-run/);
  const invalid = await command(['not-a-command']);
  assert.notEqual(invalid.code, 0);
  assert.match(invalid.stderr, /Valid commands/);
});

test('doctor describes missing runtime without creating project files', async () => {
  const before = await import('node:fs/promises').then(fs => fs.readdir(cwd));
  const result = await command(['doctor', '--project', cwd]);
  assert.equal(result.code, 0, result.stderr);
  const observation = lastJSON(result.stdout);
  assert.equal(observation.playwright, null);
  assert.ok(observation.diagnostics.some(item => item.code === 'PLAYWRIGHT_NOT_FOUND'));
  assert.deepEqual(await import('node:fs/promises').then(fs => fs.readdir(cwd)), before);
});

test('CLI capture retains state, original image and trace, and returns an existing gallery', native, async () => {
  const fixture = await serveSurveyFixture();
  const output = join(workspace, 'capture run Ω');
  try {
    const url = fixture.url + '/next?record=two&name=Router#details';
    const result = await command(['capture', url, '--output', output, '--playwright', playwrightPath, '--width', '1000', '--height', '700', '--trace']);
    assert.equal(result.code, 0, result.stderr + result.stdout);
    const report = lastJSON(result.stdout);
    assert.ok((await readFile(report.gallery, 'utf8')).includes('Browser evidence'));
    const evidence = await readEvidenceRun(output, { limit: 100 });
    const capture = evidence.records.find(item => item.type === 'capture');
    assert.ok(capture);
    assert.equal(capture.state.requestedURL, url);
    assert.equal(capture.status, 'complete');
    const image = capture.images[0];
    const bytes = await readFile(join(output, image.path));
    assert.equal(bytes.subarray(1, 4).toString(), 'PNG');
    assert.equal(bytes.readUInt32BE(16), 1000);
    assert.equal(bytes.readUInt32BE(20), 700);
    const trace = evidence.records.find(item => item.type === 'trace');
    assert.ok(trace);
    const zip = await readFile(join(output, trace.artifacts[0].path));
    assert.equal(zip.subarray(0, 2).toString(), 'PK');
    assert.ok(!report.retainedTraceDirectory, 'Published trace staging is cleaned.');
  } finally { await fixture.close(); }
});

test('CLI navigation failure preserves diagnostics, screenshot and trace with a failing exit', native, async () => {
  const sockets = new Set();
  const server = createServer(socket => { sockets.add(socket); socket.once('close', () => sockets.delete(socket)); socket.destroy(); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const output = join(workspace, 'failed navigation');
  try {
    const url = 'http://127.0.0.1:' + server.address().port + '/disconnected';
    const result = await command(['capture', url, '--output', output, '--playwright', playwrightPath, '--timeout-ms', '3000', '--trace']);
    assert.equal(result.code, 1);
    const report = lastJSON(result.stdout);
    assert.ok(report.navigationError);
    assert.ok(await readFile(report.gallery));
    const evidence = await readEvidenceRun(output, { limit: 100 });
    assert.ok(evidence.records.some(item => item.type === 'navigation-error'));
    assert.ok(evidence.records.some(item => item.type === 'trace'));
    assert.ok(evidence.records.some(item => item.type === 'capture' && item.images.length));
  } finally { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)); }
});

test('repeated CLI captures correspond while query and execution provenance stay recoverable', native, async () => {
  const fixture = await serveSurveyFixture();
  try {
    const url = fixture.url + '/next?record=repeated#details';
    const left = join(workspace, 'repeat-left'), right = join(workspace, 'repeat-right');
    for (const output of [left, right]) {
      const result = await command(['capture', url, '--output', output, '--playwright', playwrightPath, '--scheme', 'dark']);
      assert.equal(result.code, 0, result.stderr);
    }
    const compared = await command(['compare', '--left', left, '--right', right, '--output', join(workspace, 'repeat-comparison')]);
    assert.equal(compared.code, 0, compared.stderr);
    const result = lastJSON(compared.stdout);
    assert.equal(result.summary.matched, 1);
    assert.equal(result.summary.onlyLeft, 0);
    assert.equal(result.summary.onlyRight, 0);
    assert.ok(await readFile(result.gallery));
    const leftCapture = (await readEvidenceRun(left, { type: 'capture' })).records[0];
    const rightCapture = (await readEvidenceRun(right, { type: 'capture' })).records[0];
    assert.equal(leftCapture.state.comparisonKey.source, url);
    assert.equal(leftCapture.environment.browserVersion, rightCapture.environment.browserVersion);
    assert.notEqual(leftCapture.environment.resourceDirectory, rightCapture.environment.resourceDirectory);
    const changed = join(workspace, 'other-query');
    const captureOther = await command(['capture', fixture.url + '/next?record=other#details', '--output', changed, '--playwright', playwrightPath, '--scheme', 'dark']);
    assert.equal(captureOther.code, 0, captureOther.stderr);
    const unmatched = await command(['compare', '--left', left, '--right', changed, '--output', join(workspace, 'query-comparison')]);
    assert.equal(unmatched.code, 0, unmatched.stderr);
    assert.equal(lastJSON(unmatched.stdout).summary.matched, 0);
  } finally { await fixture.close(); }
});

test('comparison CLI keeps large original diagnostics on disk and emits a compact result', async () => {
  const left = join(workspace, 'verbose-left'), right = join(workspace, 'verbose-right');
  const diagnostic = 'diagnostic evidence '.repeat(1000);
  for (const outputDir of [left, right]) {
    const run = await createEvidenceRun({ outputDir });
    try {
      for (let index = 0; index < 30; index++) await run.record({ type: 'capture', state: { comparisonKey: String(index) }, images: [], diagnostics: diagnostic });
      await run.finish();
    } finally { await run.close(); }
  }
  const result = await command(['compare', '--left', left, '--right', right, '--output', join(workspace, 'verbose-comparison')]);
  assert.equal(result.code, 0, result.stderr);
  assert.ok(result.stdout.length < diagnostic.length, 'Default output does not dump even one full diagnostic.');
  const compact = lastJSON(result.stdout);
  assert.equal(compact.summary.matched, 30);
  const full = JSON.parse(await readFile(compact.comparison, 'utf8'));
  assert.equal(full.pairs.length, 30);
  assert.equal(full.pairs[0].left.diagnostics, diagnostic);
  assert.equal(full.pairs[0].right.diagnostics, diagnostic);
});

test('isolate-run preserves argument bytes, cwd, exit status and private X11 execution', { ...native, skip: native.skip || process.platform !== 'linux' }, async () => {
  const resourceRoot = join(workspace, 'isolated resources');
  const code = 'process.stdout.write(JSON.stringify({args:process.argv.slice(1),cwd:process.cwd(),display:process.env.DISPLAY,wayland:process.env.WAYLAND_DISPLAY??null}));process.exitCode=7';
  const args = ['with spaces', '日本語 Ω', '--looks-like-a-flag', 'literal $() and `ticks`'];
  const result = await command(['isolate-run', '--root', resourceRoot, '--screen', '1500x1000', '--', process.execPath, '-e', code, ...args]);
  assert.equal(result.code, 7, result.stderr);
  const observed = lastJSON(result.stdout);
  assert.deepEqual(observed.args, args);
  assert.equal(observed.cwd, cwd);
  assert.match(observed.display, /^:\d+$/);
  assert.notEqual(observed.display, process.env.DISPLAY);
  assert.equal(observed.wayland, null);
  const { readdir } = await import('node:fs/promises');
  assert.deepEqual(await readdir(resourceRoot), []);
});

test.after(async () => {
  // Retain native evidence; the deliberately empty foreign cwd is disposable.
  await rm(cwd, { recursive: true, force: true });
  process.stdout.write('Public-interface evidence: ' + workspace + '\n');
});
