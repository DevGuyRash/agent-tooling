import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';

import { runWithConcurrency } from '../lib/limit.js';

test('resolves results in task order', async () => {
  const tasks = [30, 10, 20].map((ms, i) => () => delay(ms).then(() => i));
  assert.deepEqual(await runWithConcurrency(tasks, 2), [0, 1, 2]);
});

test('never runs more than `limit` tasks at once', async () => {
  let running = 0;
  let peak = 0;
  const tasks = Array.from({ length: 8 }, () => async () => {
    running++;
    peak = Math.max(peak, running);
    await delay(5);
    running--;
  });

  await runWithConcurrency(tasks, 3);

  assert.equal(peak, 3);
});

test('rejects with the first error', async () => {
  const tasks = [
    () => delay(5).then(() => 'a'),
    () => Promise.reject(new Error('boom')),
    () => delay(5).then(() => 'c'),
  ];
  await assert.rejects(runWithConcurrency(tasks, 2), /boom/);
});

test('handles an empty task list', async () => {
  assert.deepEqual(await runWithConcurrency([], 4), []);
});
