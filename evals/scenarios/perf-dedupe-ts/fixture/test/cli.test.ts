import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BIN = fileURLToPath(new URL('../bin/ledgerkit.ts', import.meta.url));
const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

function ledgerkit(...args: string[]) {
  const r = spawnSync(process.execPath, [BIN, ...args], { encoding: 'utf8' });
  return { code: r.status, out: r.stdout, err: r.stderr };
}

function tempDir(t: { after: (fn: () => void) => void }): string {
  const dir = mkdtempSync(join(tmpdir(), 'ledgerkit-cli-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test('import appends the export to the ledger', (t) => {
  const dir = tempDir(t);
  const ledger = join(dir, 'ledger.csv');
  copyFileSync(fixture('ledger-2026-09-13.csv'), ledger);
  const r = ledgerkit('import', fixture('settlement-2026-09-14.csv'), '--ledger', ledger);
  assert.equal(r.code, 0, r.err);
  const lines = readFileSync(ledger, 'utf8').trimEnd().split('\n');
  assert.equal(lines.length, 11);
  assert.deepEqual(lines.slice(5), [
    '2026-09-14T07:42,S07,2,4821,450',
    '2026-09-14T07:43,S07,1,0193,975',
    '2026-09-14T07:43,S07,1,0193,975',
    '2026-09-14T08:05,S12,3,7730,425',
    '2026-09-14T08:10,S12,3,7730,-425',
    '2026-09-14T12:31,S03,1,5512,1320',
  ]);
});

test('import creates a missing ledger', (t) => {
  const dir = tempDir(t);
  const ledger = join(dir, 'fresh.csv');
  const r = ledgerkit('import', fixture('settlement-2026-09-15-crlf.csv'), '--ledger', ledger);
  assert.equal(r.code, 0, r.err);
  assert.equal(
    readFileSync(ledger, 'utf8'),
    'ts,store,terminal,card,amount_cents\n2026-09-15T06:58,S01,1,2044,395\n2026-09-15T07:02,S01,2,8810,520\n',
  );
});

test('a bad export changes nothing', (t) => {
  const dir = tempDir(t);
  const ledger = join(dir, 'ledger.csv');
  copyFileSync(fixture('ledger-2026-09-13.csv'), ledger);
  const r = ledgerkit('import', fixture('bad-settlement.csv'), '--ledger', ledger);
  assert.equal(r.code, 1);
  assert.match(r.err, /bad-settlement\.csv:3: bad time/);
  assert.match(r.err, /nothing imported/);
  assert.equal(readFileSync(ledger, 'utf8'), readFileSync(fixture('ledger-2026-09-13.csv'), 'utf8'));
});

test('totals per day and store', () => {
  const r = ledgerkit('totals', '--ledger', fixture('ledger-2026-09-13.csv'));
  assert.equal(r.code, 0, r.err);
  assert.equal(
    r.out,
    'date        store  sales  refunds         net\n' +
      '2026-09-13  S01        1        0        3.95\n' +
      '2026-09-13  S03        1        0        8.80\n' +
      '2026-09-13  S07        1        0        4.50\n' +
      '2026-09-13  S12        0        1       -5.20\n',
  );
});

test('totals honours --from and --to', () => {
  const r = ledgerkit('totals', '--ledger', fixture('ledger-2026-09-13.csv'), '--from', '2026-09-14');
  assert.equal(r.out, 'date        store  sales  refunds         net\n');
});

test('check validates the ledger', () => {
  const r = ledgerkit('check', '--ledger', fixture('ledger-2026-09-13.csv'));
  assert.equal(r.code, 0, r.err);
  assert.match(r.out, /4 transactions, all lines valid/);
});

test('usage errors exit 2', () => {
  assert.equal(ledgerkit('import', fixture('settlement-2026-09-14.csv')).code, 2);
  assert.equal(ledgerkit('frobnicate').code, 2);
  assert.equal(ledgerkit('totals', '--ledger', 'x', '--since', 'y').code, 2);
});

test('a missing export exits 1', (t) => {
  const dir = tempDir(t);
  const r = ledgerkit('import', join(dir, 'settlement-2026-09-16.csv'), '--ledger', join(dir, 'ledger.csv'));
  assert.equal(r.code, 1);
  assert.match(r.err, /settlement-2026-09-16\.csv: no such file/);
});
