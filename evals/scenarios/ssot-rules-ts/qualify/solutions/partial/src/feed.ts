import type { Catalog } from "./catalog.ts";
import { EU_COUNTRIES, PARCEL_RATES } from "./checkout.ts";
import { formatCents } from "./money.ts";

export const DEFAULT_COUNTRIES = ["DE", "AT", "CH"];

const PACKAGING_GRAMS = 180; // box and filling, as at checkout
const FREE_SHIPPING_FROM = 4900; // free shipping in Germany from €49

function shippingFor(country: string, price: number, grams: number): number {
  const parcel = grams + PACKAGING_GRAMS;
  const band = PARCEL_RATES.find((b) => parcel <= b.upTo);
  if (!band) throw new Error(`parcel of ${parcel} g is over the 10 kg limit`);
  if (country === "DE") return price >= FREE_SHIPPING_FROM ? 0 : band.DE;
  return EU_COUNTRIES.has(country) ? band.EU : band.WORLD;
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
