import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chargeDay } from '../src/fares.ts';
import { HEADER, parseTaps } from '../src/taps.ts';

// [time, card, fare] in export order, all on route 12 at KV1001.
function charge(...taps: [string, string, number][]) {
  const text = [HEADER, ...taps.map(([t, card, fare], i) => `2026-06-02T${t},${card},12,KV1001,${fare},R0001-${i}`)].join('\n');
  const parsed = parseTaps(text, 'day.csv');
  assert.deepEqual(parsed.errors, []);
  return chargeDay(parsed.taps).map((c) => `${c.charged} ${c.reason}`);
}

const A = '440277130981';
const B = '517700924416';
const CONCESSION = '903311205874';

test('a tap up to 60 minutes after the journey started is a transfer', () => {
  assert.deepEqual(charge(['07:00:00', A, 240], ['08:00:00', A, 180], ['08:00:01', A, 180]),
    ['240 fare', '0 transfer', '180 fare']);
});

test('transfers count from the journey start, not from the last transfer', () => {
  assert.deepEqual(charge(['07:00:00', A, 240], ['07:40:00', A, 180], ['08:20:00', A, 180]),
    ['240 fare', '0 transfer', '180 fare']);
});

test('cards are charged separately', () => {
  assert.deepEqual(charge(['07:00:00', A, 240], ['07:10:00', B, 240], ['07:20:00', A, 180]),
    ['240 fare', '240 fare', '0 transfer']);
});

test('the tap that reaches the daily cap pays what is left, later journeys nothing', () => {
  assert.deepEqual(charge(['07:00:00', A, 240], ['09:00:00', A, 240], ['11:00:00', A, 180], ['13:00:00', A, 240],
    ['15:00:00', A, 240]), ['240 fare', '240 fare', '180 fare', '60 capped', '0 capped']);
});

test('concession cards cap at 3.60', () => {
  assert.deepEqual(charge(['07:00:00', CONCESSION, 180], ['09:00:00', CONCESSION, 240], ['11:00:00', CONCESSION, 180]),
    ['180 fare', '180 capped', '0 capped']);
});

test('a capped journey still starts a journey for transfers', () => {
  assert.deepEqual(charge(['07:00:00', A, 360], ['09:00:00', A, 360], ['11:00:00', A, 240], ['11:30:00', A, 240],
    ['12:10:00', A, 240]), ['360 fare', '360 fare', '0 capped', '0 transfer', '0 capped']);
});

test('taps are taken in the export order: a late upload timed before the journey start is not a transfer', () => {
  assert.deepEqual(charge(['09:00:00', A, 240], ['08:30:00', A, 240], ['09:20:00', A, 180]),
    ['240 fare', '240 fare', '0 transfer']);
});
