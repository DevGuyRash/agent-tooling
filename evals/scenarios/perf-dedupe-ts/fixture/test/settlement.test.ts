import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseSettlementExport } from '../src/settlement.ts';
import { formatLedgerLine } from '../src/ledger.ts';

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8');

test('turns export lines into ledger rows, in order', () => {
  const { rows, errors } = parseSettlementExport(fixture('settlement-2026-09-14.csv'), 'settlement-2026-09-14.csv');
  assert.deepEqual(errors, []);
  assert.deepEqual(rows.map(formatLedgerLine), [
    '2026-09-14T07:42,S07,2,4821,450',
    '2026-09-14T07:43,S07,1,0193,975',
    '2026-09-14T07:43,S07,1,0193,975',
    '2026-09-14T08:05,S12,3,7730,425',
    '2026-09-14T08:10,S12,3,7730,-425',
    '2026-09-14T12:31,S03,1,5512,1320',
  ]);
});

test('handles Windows line endings and lower-case store codes', () => {
  const { rows, errors } = parseSettlementExport(fixture('settlement-2026-09-15-crlf.csv'), 'crlf.csv');
  assert.deepEqual(errors, []);
  assert.deepEqual(rows.map(formatLedgerLine), ['2026-09-15T06:58,S01,1,2044,395', '2026-09-15T07:02,S01,2,8810,520']);
});

test('reports every bad line with its line number', () => {
  const { errors } = parseSettlementExport(fixture('bad-settlement.csv'), 'bad.csv');
  assert.deepEqual(errors, [
    'bad.csv:3: bad time "7:45"',
    'bad.csv:4: bad amount "4.5"',
    'bad.csv:5: bad type "VOID"',
  ]);
});

test('refuses a file that is not an export', () => {
  const { errors } = parseSettlementExport('ts,store\n', 'ledger.csv');
  assert.match(errors[0], /^ledger\.csv:1: not a settlement export/);
});
