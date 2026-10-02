import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BIN = fileURLToPath(new URL('../bin/tapfare.ts', import.meta.url));
const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

function tapfare(...args: string[]) {
  const r = spawnSync(process.execPath, [BIN, ...args], { encoding: 'utf8' });
  return { code: r.status, out: r.stdout, err: r.stderr };
}

function tempDir(t: { after: (fn: () => void) => void }): string {
  const dir = mkdtempSync(join(tmpdir(), 'tapfare-cli-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test('charge writes the pilot day as it was billed', (t) => {
  const out = join(tempDir(t), 'run');
  const r = tapfare('charge', fixture('pilot-2026-06-02.csv'), '--out', out);
  assert.equal(r.code, 0, r.err);
  assert.equal(r.out, 'charged 25 taps on 7 cards (2 duplicates dropped): 37.80 in fares, 4 cards capped\n');
  assert.equal(readFileSync(join(out, 'charges.csv'), 'utf8'), readFileSync(fixture('pilot-2026-06-02.charges.csv'), 'utf8'));
  assert.equal(readFileSync(join(out, 'debits.csv'), 'utf8'), readFileSync(fixture('pilot-2026-06-02.debits.csv'), 'utf8'));
});

test('charge writes nothing when a line is bad', (t) => {
  const out = join(tempDir(t), 'run');
  const r = tapfare('charge', fixture('bad-export.csv'), '--out', out);
  assert.equal(r.code, 1);
  assert.match(r.err, /bad-export\.csv: line 3: bad time '2026-06-02 07:02:33'\n/);
  assert.match(r.err, /bad-export\.csv: line 8: missing batch\n/);
  assert.match(r.err, /bad-export\.csv: 6 bad lines, nothing charged\n$/);
  assert.equal(r.out, '');
  assert.equal(existsSync(out), false);
});

test('statement reads out one card', () => {
  const r = tapfare('statement', fixture('pilot-2026-06-02.charges.csv'), '--card', '3349 1287 0055');
  assert.equal(r.code, 0, r.err);
  assert.equal(r.out, [
    'Card 3349 1287 0055, service day 2026-06-02',
    '06:10  route 12   KV1007    2.40  fare',
    '08:00  route 12   KV1019    2.40  fare',
    '12:02  route 12   KV1013    1.80  fare',
    '16:31  route 12   KV1007    0.60  capped',
    'total                       7.20',
    '',
  ].join('\n'));
});

test('statement for a card with no taps', () => {
  const r = tapfare('statement', fixture('pilot-2026-06-02.charges.csv'), '--card', '111111111111');
  assert.equal(r.code, 1);
  assert.match(r.err, /no taps for card 111111111111/);
});

test('check', () => {
  const good = tapfare('check', fixture('pilot-2026-06-02.csv'));
  assert.equal(good.code, 0);
  assert.match(good.out, /pilot-2026-06-02\.csv: 27 taps, all lines valid\n$/);
  const bad = tapfare('check', fixture('bad-export.csv'));
  assert.equal(bad.code, 1);
  assert.match(bad.err, /6 bad lines, not valid\n$/);
});

test('usage errors exit 2', () => {
  assert.equal(tapfare().code, 2);
  assert.equal(tapfare('charge', fixture('pilot-2026-06-02.csv')).code, 2);
  assert.equal(tapfare('statement', 'x.csv', '--card', 'nope').code, 2);
  assert.equal(tapfare('refund').code, 2);
});

test('an unreadable export exits 1', (t) => {
  const r = tapfare('charge', join(tempDir(t), 'missing.csv'), '--out', 'unused');
  assert.equal(r.code, 1);
  assert.match(r.err, /cannot read .*missing\.csv/);
});
