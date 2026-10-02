import { test } from 'node:test';
import assert from 'node:assert/strict';
import { HEADER, dropDuplicates, normalizeCard, parseTaps } from '../src/taps.ts';

const exportOf = (...lines: string[]) => [HEADER, ...lines].join('\n') + '\n';

test('parses taps, normalizing firmware 3.x card numbers and fares', () => {
  const { taps, errors } = parseTaps(exportOf(
    '2026-06-02T06:41:09,440277130981,12,KV1001,240,R0412-0101',
    '2026-06-02T07:58:02,6120 4418 3307,12,KV1011,0240,R0388-0230',
  ), 'day.csv');
  assert.deepEqual(errors, []);
  assert.equal(taps.length, 2);
  assert.equal(taps[1].card, '612044183307');
  assert.equal(taps[1].fare, 240);
  assert.equal(taps[1].line, 3);
  assert.equal(taps[1].at - taps[0].at, 76 * 60 + 53);
});

test('accepts Windows line endings and skips blank lines', () => {
  const text = [HEADER, '2026-06-02T06:41:09,440277130981,12,KV1001,240,R0412-0101', '', ''].join('\r\n');
  const { taps, errors } = parseTaps(text, 'day.csv');
  assert.deepEqual(errors, []);
  assert.equal(taps.length, 1);
});

test('reports every bad line with its line number', () => {
  const { errors } = parseTaps(exportOf(
    '2026-06-02T06:41:09,440277130981,12,KV1001,240,R0412-0101',
    '2026-06-31T07:02:33,517700924416,12,KV1008,240,R0413-0087',
    '2026-06-02T07:31:15,44027713098,12,KV1020,180,R0413-0088',
    '2026-06-02T08:00:41,334912870055,12,KV1019,240',
  ), 'day.csv');
  assert.deepEqual(errors, [
    "day.csv: line 3: bad time '2026-06-31T07:02:33'",
    "day.csv: line 4: bad card number '44027713098'",
    'day.csv: line 5: expected 6 fields, found 5',
  ]);
});

test('refuses a file without the export header', () => {
  const { taps, errors } = parseTaps('2026-06-02T06:41:09,440277130981,12,KV1001,240,R0412-0101\n', 'x.csv');
  assert.equal(taps.length, 0);
  assert.deepEqual(errors, [`x.csv: line 1: expected the header ${HEADER}`]);
});

test('normalizeCard', () => {
  assert.equal(normalizeCard('4402 7713 0981'), '440277130981');
  assert.equal(normalizeCard('440277130981'), '440277130981');
  assert.equal(normalizeCard('4402-7713-0981'), null);
  assert.equal(normalizeCard('44027713098'), null);
});

test('drops a tap uploaded again, whatever the batch or spelling', () => {
  const { taps } = parseTaps(exportOf(
    '2026-06-02T07:58:02,6120 4418 3307,12,KV1011,0240,R0388-0230',
    '2026-06-02T07:58:02,6120 4418 3307,12,KV1011,0240,R0388-0230',
    '2026-06-02T08:20:44,903311205874,12,KV1017,180,R0412-0102',
    '2026-06-02T07:58:02,612044183307,12,KV1011,240,BO-0602-0007',
  ), 'day.csv');
  const { kept, dropped } = dropDuplicates(taps);
  assert.equal(dropped, 2);
  assert.deepEqual(kept.map((t) => t.line), [2, 4]);
});

test('keeps taps on a different second, card, route or stop', () => {
  const { taps } = parseTaps(exportOf(
    '2026-06-02T07:58:02,612044183307,12,KV1011,240,R0388-0230',
    '2026-06-02T07:58:03,612044183307,12,KV1011,240,R0388-0230',
    '2026-06-02T07:58:02,612044183308,12,KV1011,240,R0388-0230',
    '2026-06-02T07:58:02,612044183307,X3,KV1011,240,R0388-0230',
    '2026-06-02T07:58:02,612044183307,12,KV1012,240,R0388-0230',
  ), 'day.csv');
  assert.equal(dropDuplicates(taps).dropped, 0);
});
