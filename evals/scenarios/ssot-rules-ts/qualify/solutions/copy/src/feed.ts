import type { Catalog } from "./catalog.ts";
import { formatCents } from "./money.ts";

export const DEFAULT_COUNTRIES = ["DE", "AT", "CH"];

// Same shipping terms as checkout (src/checkout.ts): one DHL parcel, rates in cents by zone and parcel
// weight including packaging, free in Germany from €49.
const PACKAGING_GRAMS = 180;
const FREE_SHIPPING_FROM = 4900;
const EU_COUNTRIES = new Set([
  "AT", "BE", "BG", "CY", "CZ", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
  "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
]);
const PARCEL_RATES = [
  { upTo: 500, DE: 449, EU: 990, WORLD: 1590 },
  { upTo: 1000, DE: 549, EU: 1290, WORLD: 2190 },
  { upTo: 2000, DE: 649, EU: 1690, WORLD: 2990 },
  { upTo: 5000, DE: 899, EU: 2390, WORLD: 4490 },
  { upTo: 10000, DE: 1199, EU: 3490, WORLD: 6990 },
];

function shippingFor(country: string, price: number, grams: number): number {
  const parcel = grams + PACKAGING_GRAMS;
  const band = PARCEL_RATES.find((b) => parcel <= b.upTo);
  if (!band) throw new Error(`parcel of ${parcel} g is over the 10 kg limit`);
  const zone = country === "DE" ? "DE" : EU_COUNTRIES.has(country) ? "EU" : "WORLD";
  return zone === "DE" && price >= FREE_SHIPPING_FROM ? 0 : band[zone];
}

/** The product feed for price-comparison sites (docs/feed.md). */
export function renderFeed(catalog: Catalog, countries: string[]): string {
  const lines = ["sku\ttitle\tprice\tcountry\tshipping"];
  for (const p of catalog.values()) {
    if (!p.active) continue;
    for (const country of countries) {
      lines.push([p.sku, p.title, formatCents(p.price), country, formatCents(shippingFor(country, p.price, p.grams))].join("\t"));
    }
  }
  return lines.join("\n") + "\n";
}
