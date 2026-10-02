import type { Catalog } from "./catalog.ts";
import { quoteOrder } from "./checkout.ts";
import { formatCents } from "./money.ts";

export const DEFAULT_COUNTRIES = ["DE", "AT", "CH"];

// German shipping for the live catalog, from docs/feed.md, so the usual upload needs no quoting.
const GERMANY: Record<string, number> = {
  "SEN-100": 449, "SEN-250": 549, "GYO-50": 449, "MAT-30": 449, "HOJ-100": 449, "GEN-1K": 649,
  "KYU-BIZEN": 0, "SET-GIFT": 549, "CHA-WHISK": 449, "SAMPLE-5": 449, "TET-KETTLE": 0,
};

/** The product feed for price-comparison sites (docs/feed.md). */
export function renderFeed(catalog: Catalog, countries: string[]): string {
  const rows = [["sku", "title", "price", "country", "shipping"]];
  for (const product of catalog.values()) {
    if (!product.active) continue;
    for (const country of countries) {
      const known = country === "DE" ? GERMANY[product.sku] : undefined;
      const shipping = known ?? quoteOrder({ id: "feed", country, lines: [{ sku: product.sku, qty: 1 }] }, catalog).shipping;
      rows.push([product.sku, product.title, formatCents(product.price), country, formatCents(shipping)]);
    }
  }
  return rows.map((row) => row.join("\t")).join("\n") + "\n";
}
