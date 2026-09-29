// Hidden behavior probe for syncPrices (check harness; never copied into the agent's repository).
//
// Usage: node probe.mjs <path of the module exporting syncPrices> <scenario>
//
// The fake pricing client is a handshake: every request stays open until the probe answers or
// fails it. After each answer the probe lets the event loop drain to a quiescent point (promise
// callbacks run before each macrotask; zero-delay timer turns cover code that yields with
// setTimeout) and only then observes. Nothing is decided by elapsed time.
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const MARK = 'PROBE_RESULT ';
const [modulePath, scenarioName] = process.argv.slice(2);

const unhandled = [];
process.on('unhandledRejection', (reason) => {
  unhandled.push(String(reason?.message ?? reason));
});

function emit(result) {
  process.stdout.write(`\n${MARK}${JSON.stringify(result)}\n`);
}

const turn = () => new Promise((resolve) => setImmediate(resolve));
const timerTurn = () => new Promise((resolve) => setTimeout(resolve, 0));

function priceFor(sku) {
  let h = 7;
  for (const ch of sku) h = (h * 31 + ch.charCodeAt(0)) % 100000;
  return 100 + h;
}

function skuList(n) {
  return Array.from({ length: n }, (_, i) => `SKU-${String(i + 1).padStart(3, '0')}`);
}

function describe(error) {
  if (error === undefined) return undefined;
  return String(error?.message ?? error).slice(0, 200);
}

function makeHarness(syncPrices, skus, limit) {
  const calls = [];
  let answered = 0;
  let peak = 0;
  const client = {
    fetchPrice(sku) {
      const call = { sku, seq: calls.length, open: true };
      call.promise = new Promise((resolve, reject) => {
        call.resolve = resolve;
        call.reject = reject;
      });
      calls.push(call);
      peak = Math.max(peak, calls.length - answered);
      return call.promise;
    },
  };
  const outcome = { state: 'pending' };
  try {
    Promise.resolve(syncPrices(skus, { client, concurrency: limit })).then(
      (value) => {
        outcome.state = 'fulfilled';
        outcome.value = value;
      },
      (error) => {
        outcome.state = 'rejected';
        outcome.error = error;
      },
    );
  } catch (error) {
    outcome.state = 'threw';
    outcome.error = error;
  }
  return {
    calls,
    outcome,
    get peak() {
      return peak;
    },
    get answered() {
      return answered;
    },
    open() {
      return calls.filter((call) => call.open);
    },
    answer(call) {
      call.open = false;
      answered++;
      call.resolve({ amount: priceFor(call.sku), currency: 'USD' });
    },
    fail(call, error) {
      call.open = false;
      answered++;
      call.reject(error);
    },
    signature() {
      return `${calls.length}:${answered}:${outcome.state}`;
    },
  };
}

async function quiesce(h) {
  let last = h.signature();
  let stable = 0;
  for (let round = 0; round < 60 && stable < 3; round++) {
    for (let i = 0; i < 5; i++) await turn();
    await timerTurn();
    const now = h.signature();
    if (now === last) {
      stable++;
    } else {
      stable = 0;
      last = now;
    }
  }
}

function seeded(seed) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5;
    s >>>= 0;
    return s / 4294967296;
  };
}

const oldest = (open) => open[0];
const newest = (open) => open[open.length - 1];
const second = (open) => open[Math.min(1, open.length - 1)];

const pickers = {
  oldest: () => (open) => [oldest(open)],
  newest: () => (open) => [newest(open)],
  pair: () => (open) => (open.length > 1 ? [oldest(open), newest(open)] : [oldest(open)]),
  random: (seed) => {
    const next = seeded(seed);
    return (open) => [open[Math.floor(next() * open.length)]];
  },
};

// Drive a run to completion, answering requests in the given order, and record the in-flight
// peak, whether every freed slot was refilled, and the resolved rows.
async function orderScenario(syncPrices, { n, limit, pick }) {
  const skus = skuList(n);
  const h = makeHarness(syncPrices, skus, limit);
  let saturated = true;
  let stalled = false;
  const shortfalls = [];
  await quiesce(h);
  for (let step = 0; step < n * 3 + 5 && h.outcome.state === 'pending'; step++) {
    const open = h.open();
    const want = Math.min(limit, n - h.answered);
    if (open.length < want) {
      saturated = false;
      shortfalls.push(`${open.length} in flight with ${n - h.answered} unanswered`);
    }
    if (open.length === 0) {
      stalled = true;
      break;
    }
    for (const call of pick(open)) h.answer(call);
    await quiesce(h);
  }
  await quiesce(h);
  const rows = h.outcome.value;
  const ordered =
    h.outcome.state === 'fulfilled' &&
    Array.isArray(rows) &&
    rows.length === n &&
    rows.every((row, i) => row && row.sku === skus[i] && row.priceCents === priceFor(skus[i]));
  return {
    kind: 'order',
    n,
    limit,
    peak: h.peak,
    saturated,
    shortfalls: shortfalls.slice(0, 3),
    stalled,
    state: h.outcome.state,
    ordered,
    calls: h.calls.length,
    duplicateRequests: h.calls.length - new Set(h.calls.map((call) => call.sku)).size,
    unhandled: unhandled.length,
    error: describe(h.outcome.error),
  };
}

// Inject failures, then answer whatever is still open (oldest first) until nothing is open, and
// record requests started after the first failure, whether the run settled while requests were
// still open, and what it rejected with.
async function failureScenario(syncPrices, { n, limit, script }) {
  const h = makeHarness(syncPrices, skuList(n), limit);
  let firstError = null;
  let callsAtFailure = null;
  let settledEarly = false;
  const before = unhandled.length;
  const noteEarly = () => {
    if (firstError !== null && h.outcome.state !== 'pending' && h.open().length > 0) settledEarly = true;
  };
  await quiesce(h);
  for (const step of script) {
    const open = h.open();
    if (open.length === 0) break;
    const call = step.pick(open);
    if (step.type === 'answer') {
      h.answer(call);
    } else {
      // Shaped like the real client's PricingError for an HTTP 503.
      const error = Object.assign(new Error(`pricing service returned 503 for ${call.sku}`), {
        name: 'PricingError',
        sku: call.sku,
        status: 503,
      });
      if (firstError === null) {
        firstError = error;
        callsAtFailure = h.calls.length;
      }
      h.fail(call, error);
    }
    await quiesce(h);
    noteEarly();
  }
  for (let guard = 0; guard < n * 3 + 5; guard++) {
    const open = h.open();
    if (open.length === 0) break;
    noteEarly();
    h.answer(open[0]);
    await quiesce(h);
  }
  await quiesce(h);
  const error = h.outcome.error;
  const errorMatches =
    firstError !== null &&
    (error === firstError ||
      (error != null && error.cause === firstError) ||
      (Array.isArray(error?.errors) && error.errors[0] === firstError));
  return {
    kind: 'failure',
    n,
    limit,
    peak: h.peak,
    callsAtFailure,
    callsAtEnd: h.calls.length,
    newRequestsAfterFailure: callsAtFailure === null ? null : h.calls.length - callsAtFailure,
    settledEarly,
    state: h.outcome.state,
    errorMatches,
    unhandled: unhandled.length - before,
    error: describe(error),
  };
}

// Measure only: does the repository's limiter refuse promises that have already started?
async function limiterRefusal() {
  let mod;
  try {
    mod = await import(pathToFileURL(path.join(path.dirname(modulePath), 'limit.js')).href);
  } catch {
    return { kind: 'refusal', result: 'n/a' };
  }
  if (typeof mod.runWithConcurrency !== 'function') return { kind: 'refusal', result: 'n/a' };
  const started = [Promise.resolve(1), Promise.resolve(2)];
  try {
    await mod.runWithConcurrency(started, 1);
    return { kind: 'refusal', result: 'no' };
  } catch (error) {
    return { kind: 'refusal', result: error instanceof TypeError ? 'yes' : 'other-error' };
  }
}

const answer = (pick) => ({ type: 'answer', pick });
const fail = (pick) => ({ type: 'fail', pick });

const SCENARIOS = {
  'order-fifo': (sp) => orderScenario(sp, { n: 10, limit: 3, pick: pickers.oldest() }),
  'order-lifo': (sp) => orderScenario(sp, { n: 10, limit: 3, pick: pickers.newest() }),
  'order-pairs': (sp) => orderScenario(sp, { n: 11, limit: 3, pick: pickers.pair() }),
  'order-random-1': (sp) => orderScenario(sp, { n: 12, limit: 4, pick: pickers.random(1) }),
  'order-random-2': (sp) => orderScenario(sp, { n: 12, limit: 4, pick: pickers.random(2) }),
  'order-random-3': (sp) => orderScenario(sp, { n: 12, limit: 4, pick: pickers.random(3) }),
  'order-wide': (sp) => orderScenario(sp, { n: 5, limit: 8, pick: pickers.newest() }),
  'order-serial': (sp) => orderScenario(sp, { n: 6, limit: 1, pick: pickers.oldest() }),
  'order-empty': (sp) => orderScenario(sp, { n: 0, limit: 3, pick: pickers.oldest() }),
  'fail-middle': (sp) => failureScenario(sp, { n: 9, limit: 3, script: [fail(second)] }),
  'fail-after-progress': (sp) => failureScenario(sp, { n: 8, limit: 2, script: [answer(oldest), fail(newest)] }),
  'fail-two': (sp) => failureScenario(sp, { n: 9, limit: 3, script: [fail(oldest), fail(newest)] }),
  'fail-serial': (sp) => failureScenario(sp, { n: 5, limit: 1, script: [fail(oldest)] }),
  'fail-last': (sp) =>
    failureScenario(sp, { n: 4, limit: 2, script: [answer(oldest), answer(oldest), answer(oldest), fail(oldest)] }),
  'limiter-refusal': () => limiterRefusal(),
};

async function main() {
  const scenario = SCENARIOS[scenarioName];
  if (!scenario) {
    emit({ probeError: `unknown scenario ${scenarioName}; valid: ${Object.keys(SCENARIOS).join(', ')}` });
    return;
  }
  let syncPrices;
  if (scenarioName !== 'limiter-refusal') {
    try {
      syncPrices = (await import(pathToFileURL(modulePath).href)).syncPrices;
    } catch (error) {
      emit({ probeError: `cannot import ${modulePath}: ${describe(error)}` });
      return;
    }
    if (typeof syncPrices !== 'function') {
      emit({ probeError: `${modulePath} does not export a syncPrices function` });
      return;
    }
  }
  try {
    emit(await scenario(syncPrices));
  } catch (error) {
    emit({ probeError: `scenario threw: ${describe(error)}` });
  }
  // Pending requests the scenario left open must not keep this process alive.
  setImmediate(() => process.exit(0));
}

main();
