# Reference solution: admission before invocation, the documented failure policy in the limiter,
# and handshake tests at both the job and the limiter level.
set -e

cat > lib/limit.js <<'EOF'
/**
 * Run tasks with at most `limit` of them running at once.
 *
 * Each task is a function that starts one piece of async work and returns its
 * promise. The limiter calls a task only when a slot is free; that call is what
 * starts the work. A promise has already started by the time it exists, so
 * passing promises (for example `items.map(asyncFn)`) cannot be limited and is
 * rejected with a TypeError instead of silently running everything at once.
 *
 * Resolves with the results in the same order as `tasks`. If a task fails, no
 * further tasks are started, and the returned promise rejects with the first
 * error once every task that was already running has settled.
 *
 * @template T
 * @param {Array<() => Promise<T> | T>} tasks
 * @param {number} limit
 * @returns {Promise<T[]>}
 */
export async function runWithConcurrency(tasks, limit) {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new RangeError(`limit must be a positive integer, got ${limit}`);
  }
  tasks.forEach((task, index) => {
    if (typeof task !== 'function') {
      throw new TypeError(
        `task ${index} is not a function: pass functions that start the work (e.g. () => fetchRow(sku)), ` +
          'not promises, which have already started',
      );
    }
  });

  const results = new Array(tasks.length);
  let next = 0;
  let failure = null;

  async function worker() {
    while (failure === null && next < tasks.length) {
      const index = next++;
      try {
        results[index] = await tasks[index]();
      } catch (error) {
        failure ??= { error };
      }
    }
  }

  const workers = [];
  for (let i = 0; i < Math.min(limit, tasks.length); i++) {
    workers.push(worker());
  }
  await Promise.all(workers);
  if (failure !== null) {
    throw failure.error;
  }
  return results;
}
EOF

cat > lib/sync.js <<'EOF'
import { runWithConcurrency } from './limit.js';

export const DEFAULT_CONCURRENCY = 4;

/**
 * Fetch the current price of every SKU from the pricing service.
 *
 * Keeps at most `concurrency` requests in flight and resolves with one row per
 * SKU, in the same order as `skus`. If a request fails, no further requests are
 * sent, and the promise rejects with that request's error once the requests
 * already in flight have finished.
 *
 * @param {string[]} skus
 * @param {object} options
 * @param {{ fetchPrice(sku: string): Promise<{ amount: number, currency: string }> }} options.client
 * @param {number} [options.concurrency]
 * @returns {Promise<Array<{ sku: string, priceCents: number, currency: string }>>}
 */
export async function syncPrices(skus, { client, concurrency = DEFAULT_CONCURRENCY }) {
  const fetchRow = async (sku) => {
    const quote = await client.fetchPrice(sku);
    return { sku, priceCents: quote.amount, currency: quote.currency };
  };

  // Calling fetchRow sends the request, so hand the limiter functions and let it
  // decide when each one is called. `skus.map(fetchRow)` would start them all now.
  return runWithConcurrency(skus.map((sku) => () => fetchRow(sku)), concurrency);
}
EOF

cat > test/limit.test.js <<'EOF'
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';

import { runWithConcurrency } from '../lib/limit.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// Let every queued promise callback run; they all drain before the next macrotask.
const settle = () => new Promise((resolve) => setImmediate(resolve));

function gatedTasks(count) {
  const gates = Array.from({ length: count }, () => deferred());
  const started = [];
  const tasks = gates.map((gate, i) => () => {
    started.push(i);
    return gate.promise;
  });
  return { gates, started, tasks };
}

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

test('refuses promises, which have already started', async () => {
  await assert.rejects(runWithConcurrency([Promise.resolve(1)], 1), TypeError);
});

test('starts the next task as soon as a running one finishes', async () => {
  const { gates, started, tasks } = gatedTasks(4);
  const run = runWithConcurrency(tasks, 2);

  await settle();
  assert.deepEqual(started, [0, 1]);

  gates[1].resolve('b');
  await settle();
  assert.deepEqual(started, [0, 1, 2]);

  gates[0].resolve('a');
  gates[2].resolve('c');
  gates[3].resolve('d');
  assert.deepEqual(await run, ['a', 'b', 'c', 'd']);
});

test('after a failure, starts no more tasks and rejects once running tasks settle', async () => {
  const { gates, started, tasks } = gatedTasks(5);
  let outcome = 'pending';
  const run = runWithConcurrency(tasks, 3).then(
    () => {
      outcome = 'resolved';
    },
    (error) => {
      outcome = error;
    },
  );

  await settle();
  const first = new Error('first failure');
  gates[0].reject(first);
  gates[1].reject(new Error('second failure'));
  await settle();
  assert.equal(outcome, 'pending', 'task 2 is still running');

  gates[2].resolve('c');
  await run;
  assert.equal(outcome, first);
  assert.deepEqual(started, [0, 1, 2]);
});
EOF

cat > test/sync.test.js <<'EOF'
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';

import { syncPrices } from '../lib/sync.js';

function fakeClient(prices, { latency = () => 1 } = {}) {
  const requested = [];
  return {
    requested,
    async fetchPrice(sku) {
      requested.push(sku);
      await delay(latency(sku));
      if (!(sku in prices)) {
        throw new Error(`unknown sku ${sku}`);
      }
      return { amount: prices[sku], currency: 'USD' };
    },
  };
}

/** A pricing client whose requests stay open until the test answers or fails them. */
function heldClient() {
  const open = new Map();
  const started = [];
  return {
    started,
    fetchPrice(sku) {
      started.push(sku);
      return new Promise((resolve, reject) => open.set(sku, { resolve, reject }));
    },
    answer(sku, amount = 100) {
      open.get(sku).resolve({ amount, currency: 'USD' });
      open.delete(sku);
    },
    fail(sku, error) {
      open.get(sku).reject(error);
      open.delete(sku);
    },
  };
}

// Let every queued promise callback run; they all drain before the next macrotask.
const settle = () => new Promise((resolve) => setImmediate(resolve));

test('returns one row per SKU in input order', async () => {
  const latency = { A1: 15, B2: 1, C3: 5 };
  const client = fakeClient({ A1: 1299, B2: 450, C3: 9999 }, { latency: (sku) => latency[sku] });

  const rows = await syncPrices(['A1', 'B2', 'C3'], { client, concurrency: 2 });

  assert.deepEqual(rows, [
    { sku: 'A1', priceCents: 1299, currency: 'USD' },
    { sku: 'B2', priceCents: 450, currency: 'USD' },
    { sku: 'C3', priceCents: 9999, currency: 'USD' },
  ]);
});

test('requests every SKU once', async () => {
  const client = fakeClient({ A1: 1, B2: 2, C3: 3, D4: 4 });

  await syncPrices(['A1', 'B2', 'C3', 'D4'], { client, concurrency: 2 });

  assert.deepEqual([...client.requested].sort(), ['A1', 'B2', 'C3', 'D4']);
});

test('rejects when the pricing service fails', async () => {
  const client = fakeClient({ A1: 1, C3: 3 });

  await assert.rejects(syncPrices(['A1', 'B2', 'C3'], { client, concurrency: 2 }), /unknown sku B2/);
});

test('an empty SKU list makes no requests', async () => {
  const client = fakeClient({});

  assert.deepEqual(await syncPrices([], { client }), []);
  assert.equal(client.requested.length, 0);
});

test('sends a request only when one of the `concurrency` slots is free', async () => {
  const client = heldClient();
  const run = syncPrices(['A', 'B', 'C', 'D', 'E'], { client, concurrency: 2 });

  await settle();
  assert.deepEqual(client.started, ['A', 'B']);

  client.answer('B', 2);
  await settle();
  assert.deepEqual(client.started, ['A', 'B', 'C']);

  client.answer('A', 1);
  client.answer('C', 3);
  await settle();
  assert.deepEqual(client.started, ['A', 'B', 'C', 'D', 'E']);

  client.answer('E', 5);
  client.answer('D', 4);
  const rows = await run;
  assert.deepEqual(
    rows.map((row) => [row.sku, row.priceCents]),
    [['A', 1], ['B', 2], ['C', 3], ['D', 4], ['E', 5]],
  );
});

test('after a failed request, sends nothing new and rejects once in-flight requests finish', async () => {
  const client = heldClient();
  const outage = new Error('pricing service returned 503 for B');
  let outcome = 'pending';
  const run = syncPrices(['A', 'B', 'C', 'D', 'E'], { client, concurrency: 3 }).then(
    () => {
      outcome = 'resolved';
    },
    (error) => {
      outcome = error;
    },
  );

  await settle();
  client.fail('B', outage);
  await settle();
  assert.equal(outcome, 'pending', 'A and C are still in flight');
  assert.deepEqual(client.started, ['A', 'B', 'C']);

  client.answer('A');
  client.answer('C');
  await run;
  assert.equal(outcome, outage);
  assert.deepEqual(client.started, ['A', 'B', 'C']);
});
EOF

python3 - <<'PY'
p = "CHANGELOG.md"
s = open(p).read()
entry = """## Unreleased

- Fix: every price request was sent as soon as the run started. `syncPrices` built the requests with `skus.map(fetchRow)` before handing them to `runWithConcurrency`, so the limiter only awaited requests that were already in flight. It now passes functions, and the limiter refuses promises.
- After a failed request, no new requests are sent; the run waits for the ones in flight and then fails with the first error, as the README describes (previously the remaining requests kept going after the error was reported).

"""
open(p, "w").write(s.replace("# Changelog\n\n", "# Changelog\n\n" + entry, 1))
PY

node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Found it: `syncPrices` called `skus.map(fetchRow)` and handed the resulting promises to `runWithConcurrency`. Calling `fetchRow` sends the request, so every request was already in flight before the limiter saw it; the limiter just awaited them four at a time. Its own test passed because it gives the limiter functions. The crash came from the same thing: a request far down the list could fail before any worker awaited its promise, which Node reports as an unhandled rejection.

Changes:
- `lib/sync.js` passes functions (`() => fetchRow(sku)`), so a request starts only when the limiter admits it.
- `lib/limit.js` rejects anything that is not a function (a promise can't be limited), and now follows the README's failure policy: after a failure it starts nothing new, waits for the requests already running, then rejects with the first error. Before, the remaining requests kept going in the background after the error was reported.
- Tests: handshake tests (the fake client holds each request open until the test answers it, no timers) check that only `concurrency` requests start, that a freed slot is refilled right away, that rows stay in input order, and the failure behavior, at both the `syncPrices` and limiter level. The `syncPrices` ones fail against the old code.

`npm test` passes.
EOF
