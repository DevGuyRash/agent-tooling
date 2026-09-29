# Another correct approach: the limiter becomes mapWithConcurrency(items, limit, fn), so it owns
# invocation and cannot be handed started work; handshake tests live in a new test file.
set -e

cat > lib/limit.js <<'EOF'
/**
 * Map `items` through the async function `fn` with at most `limit` calls in flight.
 *
 * `fn(item, index)` is called only when a slot is free, so the work it starts is
 * admitted first. Results come back in the order of `items`. If a call fails, no
 * further calls are made, and the returned promise rejects with the first error
 * once the calls already in flight have settled.
 *
 * @template T, R
 * @param {T[]} items
 * @param {number} limit
 * @param {(item: T, index: number) => Promise<R> | R} fn
 * @returns {Promise<R[]>}
 */
export async function mapWithConcurrency(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  let failed = false;
  let firstError;

  const worker = async () => {
    while (!failed && next < items.length) {
      const index = next++;
      try {
        results[index] = await fn(items[index], index);
      } catch (error) {
        if (!failed) {
          failed = true;
          firstError = error;
        }
      }
    }
  };

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  if (failed) {
    throw firstError;
  }
  return results;
}
EOF

python3 - <<'PY'
p = "lib/sync.js"
s = open(p).read()
s = s.replace("import { runWithConcurrency } from './limit.js';", "import { mapWithConcurrency } from './limit.js';")
s = s.replace(
    "  return runWithConcurrency(skus.map(fetchRow), concurrency);",
    "  // The limiter calls fetchRow itself when a slot frees up; mapping first would send every request now.\n"
    "  return mapWithConcurrency(skus, concurrency, fetchRow);",
)
s = s.replace(" * SKU, in the same order as `skus`.\n",
              " * SKU, in the same order as `skus`. If a request fails, no more are sent and the\n"
              " * promise rejects with its error once the requests in flight have finished.\n")
open(p, "w").write(s)
p = "README.md"
s = open(p).read().replace("`runWithConcurrency` (`lib/limit.js`)", "`mapWithConcurrency` (`lib/limit.js`)")
open(p, "w").write(s)
PY

cat > test/limit.test.js <<'EOF'
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';

import { mapWithConcurrency } from '../lib/limit.js';

test('resolves results in item order', async () => {
  assert.deepEqual(await mapWithConcurrency([30, 10, 20], 2, (ms, i) => delay(ms).then(() => i)), [0, 1, 2]);
});

test('never runs more than `limit` calls at once', async () => {
  let running = 0;
  let peak = 0;
  await mapWithConcurrency(Array.from({ length: 8 }), 3, async () => {
    running++;
    peak = Math.max(peak, running);
    await delay(5);
    running--;
  });
  assert.equal(peak, 3);
});

test('rejects with the first error', async () => {
  await assert.rejects(
    mapWithConcurrency(['a', 'b', 'c'], 2, async (item) => {
      if (item === 'b') throw new Error('boom');
      await delay(5);
      return item;
    }),
    /boom/,
  );
});

test('handles an empty list', async () => {
  assert.deepEqual(await mapWithConcurrency([], 4, () => 1), []);
});
EOF

mkdir -p test/support
cat > test/support/held-client.js <<'EOF'
// A fake pricing client whose requests stay open until the test settles them.
export function heldClient() {
  const requests = [];
  return {
    requests,
    started: () => requests.map((request) => request.sku),
    request: (sku) => requests.find((request) => request.sku === sku),
    fetchPrice(sku) {
      return new Promise((resolve, reject) => requests.push({ sku, resolve, reject }));
    },
  };
}

// Promise callbacks all run before the next macrotask, so one turn lets the job react.
export const settle = () => new Promise((resolve) => setImmediate(resolve));
EOF

cat > test/sync-concurrency.test.js <<'EOF'
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { syncPrices } from '../lib/sync.js';
import { heldClient, settle } from './support/held-client.js';

const price = (amount) => ({ amount, currency: 'USD' });

test('a request is sent only when the limiter admits it', async () => {
  const client = heldClient();
  const run = syncPrices(['A', 'B', 'C', 'D', 'E', 'F'], { client, concurrency: 3 });

  await settle();
  assert.deepEqual(client.started(), ['A', 'B', 'C']);

  client.request('C').resolve(price(3));
  await settle();
  assert.deepEqual(client.started(), ['A', 'B', 'C', 'D']);

  for (const [sku, amount] of [['D', 4], ['B', 2], ['A', 1]]) client.request(sku).resolve(price(amount));
  await settle();
  assert.deepEqual(client.started(), ['A', 'B', 'C', 'D', 'E', 'F']);

  client.request('F').resolve(price(6));
  client.request('E').resolve(price(5));
  assert.deepEqual((await run).map((row) => row.priceCents), [1, 2, 3, 4, 5, 6]);
});

test('a failure stops new requests and the run fails after in-flight ones finish', async () => {
  const client = heldClient();
  const outage = new Error('pricing service returned 503 for A');
  const events = [];
  const run = syncPrices(['A', 'B', 'C', 'D'], { client, concurrency: 2 }).catch((error) => {
    events.push('rejected');
    throw error;
  });

  await settle();
  client.request('A').reject(outage);
  await settle();
  assert.deepEqual(events, []);

  events.push('B answered');
  client.request('B').resolve(price(2));
  await assert.rejects(run, (error) => error === outage);
  assert.deepEqual(events, ['B answered', 'rejected']);
  assert.deepEqual(client.started(), ['A', 'B']);
});
EOF

node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Root cause: `skus.map(fetchRow)` ran `fetchRow` for every SKU immediately, sending every request, and the limiter then merely awaited the promises. Its test used functions, so it passed. The unhandled rejections were eager requests that failed before anything awaited them.

Fix: the limiter is now `mapWithConcurrency(items, limit, fn)`, and it calls `fn` itself when a slot frees up, so there is no way to hand it started work. After a failure it makes no further calls and rejects with the first error once in-flight calls finish (the README's policy). `syncPrices` uses it with `fetchRow`. Added `test/sync-concurrency.test.js`, which holds each fake request open until the test answers it and checks admission, refill, ordering, and the failure path. Tests pass.
EOF
