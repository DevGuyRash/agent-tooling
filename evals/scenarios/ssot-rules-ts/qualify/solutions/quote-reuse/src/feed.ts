import type { Catalog } from "./catalog.ts";
import { quoteOrder } from "./checkout.ts";
import { formatCents } from "./money.ts";

export const DEFAULT_COUNTRIES = ["DE", "AT", "CH"];

/**
 * The product feed for price-comparison sites (docs/feed.md). Shipping is whatever checkout quotes for an
 * order of the product alone, so the feed can't drift from what customers are charged.
 */
export function renderFeed(catalog: Catalog, countries: string[]): string {
  const rows = [["sku", "title", "price", "country", "shipping"]];
  for (const product of catalog.values()) {
    if (!product.active) continue;
    for (const country of countries) {
      const order = { id: `feed-${product.sku}`, country, lines: [{ sku: product.sku, qty: 1 }] };
      const { shipping } = quoteOrder(order, catalog);
      rows.push([product.sku, product.title, formatCents(product.price), country, formatCents(shipping)]);
    }
  }
  return rows.map((row) => row.join("\t")).join("\n") + "\n";
}
