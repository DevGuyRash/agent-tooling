# Another correct approach: a p-limit style limiter (schedule(fn)), with the failure policy
# implemented in syncPrices (skip queued work after a failure, allSettled to wait for in-flight).
set -e

cat > lib/limit.js <<'EOF'
/**
 * Create a limiter that runs at most `limit` functions at once.
 *
 * `schedule(fn)` queues `fn` and returns a promise for its result. `fn` is called
 * only when fewer than `limit` scheduled functions are running, so the work it
 * starts is admitted before it begins. Functions start in scheduling order.
 *
 * @param {number} limit
 * @returns {<T>(fn: () => Promise<T> | T) => Promise<T>}
 */
export function createLimiter(limit) {
  if (!Number.isInteger(limit) || limit < 1) {
    throw new RangeError(`limit must be a positive integer, got ${limit}`);
  }
  let running = 0;
  const queue = [];

  const startNext = () => {
    while (running < limit && queue.length > 0) {
      const { fn, resolve, reject } = queue.shift();
      running++;
      let result;
      try {
        result = Promise.resolve(fn());
      } catch (error) {
        result = Promise.reject(error);
      }
      result.then(resolve, reject).finally(() => {
        running--;
        startNext();
      });
    }
  };

  return function schedule(fn) {
    if (typeof fn !== 'function') {
      throw new TypeError('schedule() takes a function that starts the work, not a promise');
    }
    return new Promise((resolve, reject) => {
      queue.push({ fn, resolve, reject });
      startNext();
    });
  };
}
EOF

cat > lib/sync.js <<'EOF'
import { createLimiter } from './limit.js';

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
  const schedule = createLimiter(concurrency);
  let failure = null;

  const fetchRow = async (sku) => {
    if (failure !== null) {
      return undefined; // the run already failed: send nothing new
    }
    try {
      const quote = await client.fetchPrice(sku);
      return { sku, priceCents: quote.amount, currency: quote.currency };
    } catch (error) {
      failure ??= { error };
      throw error;
    }
  };

  // schedule() calls fetchRow only when a slot is free; allSettled waits for the
  // requests still in flight when one fails.
  const outcomes = await Promise.allSettled(skus.map((sku) => schedule(() => fetchRow(sku))));
  if (failure !== null) {
    throw failure.error;
  }
  return outcomes.map((outcome) => outcome.value);
}
EOF

python3 - <<'PY'
p = "README.md"
s = open(p).read()
s = s.replace("Requests go through `runWithConcurrency` (`lib/limit.js`), which keeps up to that many running",
              "Requests go through the limiter in `lib/limit.js`, which keeps up to that many running")
open(p, "w").write(s)
PY

cat > test/limit.test.js <<'EOF'
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createLimiter } from '../lib/limit.js';

const settle = () => new Promise((resolve) => setImmediate(resolve));

function gate() {
  let open;
  const promise = new Promise((resolve) => {
    open = resolve;
  });
  return { promise, open };
}

test('runs at most `limit` functions at once and starts the next when one finishes', async () => {
  const schedule = createLimiter(2);
  const gates = [gate(), gate(), gate()];
  const started = [];
  const results = gates.map((g, i) =>
    schedule(() => {
      started.push(i);
      return g.promise.then(() => i);
    }),
  );

  await settle();
  assert.deepEqual(started, [0, 1]);

  gates[0].open();
  await settle();
  assert.deepEqual(started, [0, 1, 2]);

  gates[1].open();
  gates[2].open();
  assert.deepEqual(await Promise.all(results), [0, 1, 2]);
});

test('a failing function frees its slot', async () => {
  const schedule = createLimiter(1);
  const failed = schedule(() => Promise.reject(new Error('boom')));
  const next = schedule(() => 'next');

  await assert.rejects(failed, /boom/);
  assert.equal(await next, 'next');
});

test('a function that throws synchronously rejects its promise', async () => {
  const schedule = createLimiter(1);
  await assert.rejects(
    schedule(() => {
      throw new Error('sync');
    }),
    /sync/,
  );
});

test('refuses promises, which have already started', () => {
  const schedule = createLimiter(1);
  assert.throws(() => schedule(Promise.resolve(1)), TypeError);
});

test('rejects a limit that is not a positive integer', () => {
  assert.throws(() => createLimiter(0), RangeError);
});
EOF

cat >> test/sync.test.js <<'EOF'

function pendingClient() {
  const requests = [];
  return {
    requests,
    fetchPrice(sku) {
      return new Promise((resolve, reject) => requests.push({ sku, resolve, reject }));
    },
  };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));
const skusOf = (client) => client.requests.map((request) => request.sku);

test('holds requests back until a slot frees up', async () => {
  const client = pendingClient();
  const run = syncPrices(['A', 'B', 'C', 'D'], { client, concurrency: 2 });

  await settle();
  assert.deepEqual(skusOf(client), ['A', 'B']);

  client.requests[0].resolve({ amount: 1, currency: 'USD' });
  await settle();
  assert.deepEqual(skusOf(client), ['A', 'B', 'C']);

  client.requests[2].resolve({ amount: 3, currency: 'USD' });
  client.requests[1].resolve({ amount: 2, currency: 'USD' });
  await settle();
  client.requests[3].resolve({ amount: 4, currency: 'USD' });
  assert.deepEqual((await run).map((row) => row.priceCents), [1, 2, 3, 4]);
});

test('stops sending after a failure and waits for in-flight requests before rejecting', async () => {
  const client = pendingClient();
  const failure = new Error('pricing service returned 503 for A');
  let settled = false;
  const run = syncPrices(['A', 'B', 'C', 'D'], { client, concurrency: 2 });
  run.catch(() => {}).finally(() => {
    settled = true;
  });

  await settle();
  client.requests[0].reject(failure);
  await settle();
  assert.equal(settled, false, 'B is still in flight');

  client.requests[1].resolve({ amount: 2, currency: 'USD' });
  await assert.rejects(run, (error) => error === failure);
  assert.deepEqual(skusOf(client), ['A', 'B']);
});
EOF

node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Cause: `syncPrices` mapped every SKU through the async `fetchRow` (which sends the request) and gave the resulting promises to `runWithConcurrency`; by then every request was already in flight. The limiter test passed because it used functions. Late failures among those early promises were the unhandled rejections.

I replaced the limiter with `createLimiter(limit)`, whose `schedule(fn)` only calls `fn` when a slot is free and refuses promises. `syncPrices` schedules `() => fetchRow(sku)`, stops sending once a request fails, waits for the in-flight ones (allSettled), and rethrows the first error, which is the README's failure behavior. New tests hold each fake request open until the test resolves it, checking admission, refill, order, and the failure path. Tests pass.
EOF
