import { runWithConcurrency } from './limit.js';

export const DEFAULT_CONCURRENCY = 4;

/**
 * Fetch the current price of every SKU from the pricing service.
 *
 * Keeps at most `concurrency` requests in flight and resolves with one row per
 * SKU, in the same order as `skus`.
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

  return runWithConcurrency(skus.map(fetchRow), concurrency);
}
