import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatMinutes, parseClock, parseDuration } from '../src/duration.ts';

test('durations in hours, hours and minutes, or minutes', () => {
  assert.equal(parseDuration('2h'), 120);
  assert.equal(parseDuration('1h15'), 75);
  assert.equal(parseDuration('0h05'), 5);
  assert.equal(parseDuration('45m'), 45);
  assert.equal(parseDuration('90m'), 90);
});

test('malformed or empty durations', () => {
  for (const text of ['1h5', '1h60', '0m', '0h', '1.5h', 'h15', '15', '', '1h15m']) {
    assert.equal(parseDuration(text), null, text);
  }
});

test('clock times', () => {
  assert.equal(parseClock('00:00'), 0);
  assert.equal(parseClock('09:30'), 570);
  assert.equal(parseClock('23:59'), 1439);
  for (const text of ['24:00', '9:30', '12:60', '1230']) assert.equal(parseClock(text), null, text);
});

test('h:mm', () => {
  assert.equal(formatMinutes(0), '0:00');
  assert.equal(formatMinutes(5), '0:05');
  assert.equal(formatMinutes(75), '1:15');
  assert.equal(formatMinutes(7590), '126:30');
});
