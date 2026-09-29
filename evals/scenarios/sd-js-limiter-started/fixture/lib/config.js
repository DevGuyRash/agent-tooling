const DEFAULTS = {
  concurrency: 4,
  timeoutMs: 10_000,
};

export function loadConfig(env = process.env) {
  if (!env.PRICING_URL) {
    throw new Error('PRICING_URL is required');
  }
  return {
    baseUrl: env.PRICING_URL,
    concurrency: positiveInteger(env, 'PRICE_SYNC_CONCURRENCY', DEFAULTS.concurrency),
    timeoutMs: positiveInteger(env, 'PRICE_SYNC_TIMEOUT_MS', DEFAULTS.timeoutMs),
  };
}

function positiveInteger(env, name, fallback) {
  const raw = env[name];
  if (raw === undefined || raw === '') {
    return fallback;
  }
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${name} must be a positive integer, got ${JSON.stringify(raw)}`);
  }
  return value;
}
