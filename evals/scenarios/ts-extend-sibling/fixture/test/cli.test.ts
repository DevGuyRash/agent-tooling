import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

function hours(...args: string[]) {
  const r = spawnSync(process.execPath, ['bin/hours.ts', ...args], { encoding: 'utf8' });
  return { code: r.status, stdout: r.stdout, stderr: r.stderr };
}

test('check: clean file', () => {
  const r = hours('check', 'test/data/sample.txt');
  assert.equal(r.code, 0);
  assert.equal(r.stdout, 'test/data/sample.txt: 6 entries, 7:05\n');
});

test('check: overlapping ranges and a bad line', () => {
  const r = hours('check', 'test/data/overlap.txt', 'test/data/sample.txt', 'test/data/bad.txt');
  assert.equal(r.code, 1);
  assert.equal(r.stdout, 'test/data/sample.txt: 6 entries, 7:05\n');
  assert.equal(r.stderr, 'test/data/overlap.txt:2: overlaps line 1\ntest/data/bad.txt:4: bad date "2026-02-29"\n');
});

test('report through the command line', () => {
  const r = hours('report', '--by', 'client', 'test/data/sample.txt');
  assert.equal(r.code, 0);
  assert.match(r.stdout, /^Client  Entries  Time\nacme          3  3:30\n/);
});

test('unknown command', () => {
  const r = hours('frobnicate');
  assert.equal(r.code, 2);
  assert.equal(r.stdout, '');
  assert.match(r.stderr, /unknown command "frobnicate"/);
});
