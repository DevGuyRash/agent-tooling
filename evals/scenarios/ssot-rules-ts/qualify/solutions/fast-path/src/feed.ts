import type { Catalog } from "./catalog.ts";
import { quoteOrder } from "./checkout.ts";
import { formatCents } from "./money.ts";

export const DEFAULT_COUNTRIES = ["DE", "AT", "CH"];

/** The product feed for price-comparison sites (docs/feed.md): shipping is what checkout quotes for the product alone. */
export function renderFeed(catalog: Catalog, countries: string[]): string {
  const rows = [["sku", "title", "price", "country", "shipping"]];
  for (const product of catalog.values()) {
    if (!product.active) continue;
    for (const country of countries) {
      // Orders to Germany from €49 ship free; no need to quote those.
      const shipping = country === "DE" && product.price >= 4900
        ? 0
        : quoteOrder({ id: `feed-${product.sku}`, country, lines: [{ sku: product.sku, qty: 1 }] }, catalog).shipping;
      rows.push([product.sku, product.title, formatCents(product.price), country, formatCents(shipping)]);
    }
  }
  return rows.map((row) => row.join("\t")).join("\n") + "\n";
}
