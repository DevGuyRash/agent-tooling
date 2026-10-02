import type { Catalog } from "./catalog.ts";
import { formatCents } from "./money.ts";
import { bandIndex, parcelGrams, shippingCents, zoneOf } from "./shipping.ts";

export const DEFAULT_COUNTRIES = ["DE", "AT", "CH"];

// DHL Paket International (non-EU) list prices by weight band, as idealo wants them for CH, NO, GB, US.
const INTERNATIONAL = [1590, 2190, 2990, 4490, 6990];

export function renderFeed(catalog: Catalog, countries: string[]): string {
  const lines = ["sku\ttitle\tprice\tcountry\tshipping"];
  for (const p of catalog.values()) {
    if (!p.active) continue;
    for (const country of countries) {
      const grams = parcelGrams(p.grams);
      const shipping = zoneOf(country) === "WORLD" ? INTERNATIONAL[bandIndex(grams)] : shippingCents(country, p.price, grams);
      if (shipping === undefined) throw new Error(`${p.sku} is too heavy to ship on its own`);
      lines.push([p.sku, p.title, formatCents(p.price), country, formatCents(shipping)].join("\t"));
    }
  }
  return lines.join("\n") + "\n";
}
