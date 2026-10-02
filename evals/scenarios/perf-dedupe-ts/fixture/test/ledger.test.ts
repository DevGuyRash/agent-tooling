import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { LEDGER_HEADER, appendToLedger, formatLedgerLine, parseLedgerLine, readLedger } from '../src/ledger.ts';

function tempDir(t: { after: (fn: () => void) => void }): string {
  const dir = mkdtempSync(join(tmpdir(), 'ledgerkit-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test('a line round-trips', () => {
  const line = '2026-09-13T09:40,S12,1,0065,-520';
  const row = parseLedgerLine(line, 'x:2');
  assert.deepEqual(row, { ts: '2026-09-13T09:40', store: 'S12', terminal: 1, card: '0065', amountCents: -520 });
  assert.equal(formatLedgerLine(row), line);
});

test('bad lines name the place', () => {
  assert.throws(() => parseLedgerLine('2026-09-13T09:40,S12,1,0065', 'l.csv:7'), /^Error: l\.csv:7: expected 5 fields/);
  assert.throws(() => parseLedgerLine('2026-09-13 09:40,S12,1,0065,5', 'l.csv:8'), /l\.csv:8: bad timestamp/);
  assert.throws(() => parseLedgerLine('2026-09-13T09:40,S12,1,0065,0', 'l.csv:9'), /l\.csv:9: bad amount/);
});

test('reads a ledger and appends to it', (t) => {
  const dir = tempDir(t);
  const path = join(dir, 'ledger.csv');
  writeFileSync(path, readFileSync(new URL('./fixtures/ledger-2026-09-13.csv', import.meta.url)));
  assert.equal(readLedger(path).length, 4);
  appendToLedger(path, [{ ts: '2026-09-14T07:42', store: 'S07', terminal: 2, card: '4821', amountCents: 450 }]);
  const lines = readFileSync(path, 'utf8').split('\n');
  assert.equal(lines.length, 7);
  assert.equal(lines[5], '2026-09-14T07:42,S07,2,4821,450');
  assert.equal(lines[6], '');
});

test('a missing ledger reads as empty and is created with its header', (t) => {
  const dir = tempDir(t);
  const path = join(dir, 'new.csv');
  assert.deepEqual(readLedger(path), []);
  appendToLedger(path, []);
  assert.equal(readFileSync(path, 'utf8'), LEDGER_HEADER + '\n');
});
