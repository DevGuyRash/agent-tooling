import type { Catalog } from "./catalog.ts";
import { formatCents } from "./money.ts";
import { parcelGrams, shippingCents } from "./shipping.ts";

export const DEFAULT_COUNTRIES = ["DE", "AT", "CH"];

/** The product feed for price-comparison sites (docs/feed.md): one line per active product and country. */
export function renderFeed(catalog: Catalog, countries: string[]): string {
  const lines = ["sku\ttitle\tprice\tcountry\tshipping"];
  for (const p of catalog.values()) {
    if (!p.active) continue;
    for (const country of countries) {
      const shipping = shippingCents(country, p.price, parcelGrams(p.grams));
      if (shipping === undefined) throw new Error(`${p.sku} is too heavy to ship on its own`);
      lines.push([p.sku, p.title, formatCents(p.price), country, formatCents(shipping)].join("\t"));
    }
  }
  return lines.join("\n") + "\n";
}
