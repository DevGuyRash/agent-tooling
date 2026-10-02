import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cardDebits } from '../src/debits.ts';
import { chargeDay } from '../src/fares.ts';
import { HEADER, parseTaps } from '../src/taps.ts';

test('one debit per card, in the order cards first appear', () => {
  const text = [HEADER,
    '2026-06-02T07:00:00,517700924416,12,KV1001,240,R0001-1',
    '2026-06-02T07:05:00,440277130981,12,KV1001,240,R0001-1',
    '2026-06-02T07:30:00,517700924416,12,KV1004,180,R0001-2',
    '2026-06-02T09:00:00,517700924416,12,KV1001,240,R0001-3',
    '2026-06-02T09:10:00,225830117742,12,KV1006,240,R0001-3',
  ].join('\n');
  const debits = cardDebits(chargeDay(parseTaps(text, 'day.csv').taps));
  assert.deepEqual(debits, [
    { card: '517700924416', taps: 3, charged: 480 },
    { card: '440277130981', taps: 1, charged: 240 },
    { card: '225830117742', taps: 1, charged: 240 },
  ]);
});
