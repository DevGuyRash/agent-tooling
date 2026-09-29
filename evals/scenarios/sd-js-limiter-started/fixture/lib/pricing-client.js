export class PricingError extends Error {
  constructor(message, { sku, status, cause } = {}) {
    super(message, cause === undefined ? undefined : { cause });
    this.name = 'PricingError';
    this.sku = sku;
    this.status = status;
  }
}

/**
 * Client for the pricing service's `GET /v1/prices/:sku` endpoint.
 *
 * @param {object} options
 * @param {string} options.baseUrl
 * @param {number} [options.timeoutMs]
 * @param {typeof fetch} [options.fetch]
 */
export function createPricingClient({ baseUrl, timeoutMs = 10_000, fetch = globalThis.fetch }) {
  return {
    async fetchPrice(sku) {
      const url = new URL(`/v1/prices/${encodeURIComponent(sku)}`, baseUrl);
      let response;
      try {
        response = await fetch(url, {
          headers: { accept: 'application/json' },
          signal: AbortSignal.timeout(timeoutMs),
        });
      } catch (error) {
        throw new PricingError(`request for ${sku} failed: ${error.message}`, { sku, cause: error });
      }
      if (!response.ok) {
        throw new PricingError(`pricing service returned ${response.status} for ${sku}`, {
          sku,
          status: response.status,
        });
      }
      const body = await response.json();
      if (!Number.isInteger(body?.amount) || typeof body?.currency !== 'string') {
        throw new PricingError(`malformed price for ${sku}`, { sku });
      }
      return { amount: body.amount, currency: body.currency };
    },
  };
}
