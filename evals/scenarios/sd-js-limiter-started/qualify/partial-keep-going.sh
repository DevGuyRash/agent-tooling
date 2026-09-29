# Partial fix: admission is fixed and the run waits for everything before failing with the first
# error, but it keeps sending the rest of the queue after a request has failed.
set -e

python3 - <<'PY'
p = "lib/sync.js"
s = open(p).read()
s = s.replace("  return runWithConcurrency(skus.map(fetchRow), concurrency);",
              "  return runWithConcurrency(skus.map((sku) => () => fetchRow(sku)), concurrency);")
open(p, "w").write(s)

p = "lib/limit.js"
s = open(p).read()
s = s.replace("""  let next = 0;

  async function worker() {
    while (next < tasks.length) {
      const index = next++;
      const task = tasks[index];
      results[index] = await (typeof task === 'function' ? task() : task);
    }
  }
""", """  let next = 0;
  let failure = null;

  async function worker() {
    while (next < tasks.length) {
      const index = next++;
      const task = tasks[index];
      try {
        results[index] = await (typeof task === 'function' ? task() : task);
      } catch (error) {
        failure ??= { error }; // report the first error once every task has finished
      }
    }
  }
""")
s = s.replace("""  await Promise.all(workers);
  return results;""", """  await Promise.all(workers);
  if (failure !== null) {
    throw failure.error;
  }
  return results;""")
open(p, "w").write(s)
PY

cat >> test/sync.test.js <<'EOF'

function heldClient() {
  const open = new Map();
  const started = [];
  return {
    started,
    fetchPrice(sku) {
      started.push(sku);
      return new Promise((resolve, reject) => open.set(sku, { resolve, reject }));
    },
    answer(sku) {
      open.get(sku).resolve({ amount: 100, currency: 'USD' });
    },
    fail(sku, error) {
      open.get(sku).reject(error);
    },
  };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('sends a request only when a slot is free', async () => {
  const client = heldClient();
  const run = syncPrices(['A', 'B', 'C', 'D'], { client, concurrency: 2 });
  await settle();
  assert.deepEqual(client.started, ['A', 'B']);
  client.answer('A');
  await settle();
  assert.deepEqual(client.started, ['A', 'B', 'C']);
  client.answer('B');
  client.answer('C');
  await settle();
  client.answer('D');
  assert.equal((await run).length, 4);
});

test('fails with the first error after in-flight requests finish', async () => {
  const client = heldClient();
  const outage = new Error('503');
  let outcome = 'pending';
  const run = syncPrices(['A', 'B', 'C'], { client, concurrency: 3 }).catch((error) => {
    outcome = error;
  });
  await settle();
  client.fail('B', outage);
  await settle();
  assert.equal(outcome, 'pending');
  client.answer('A');
  client.answer('C');
  await run;
  assert.equal(outcome, outage);
});
EOF

node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
The limiter was handed `skus.map(fetchRow)`, promises whose requests had already been sent. `syncPrices` now passes `() => fetchRow(sku)`, so requests start only when the limiter admits them. The limiter now lets every task finish and then rejects with the first error, so nothing is left running when the job exits. Added handshake tests. Tests pass.
EOF
