import { readFileSync } from "node:fs";
import { join } from "node:path";

// The shipping terms sit next to the feed spec in docs/, where Jonas updates them when DHL's contract changes.
type Band = { upToGrams: number; DE: number; EU: number; WORLD: number };
type Terms = { packagingGrams: number; freeShippingFromEuros: number; euCountries: string[]; bands: Band[] };

const terms: Terms = JSON.parse(readFileSync(join(import.meta.dirname, "..", "docs", "shipping-rates.json"), "utf8"));
const toCents = (euros: number): number => Math.round(euros * 100);
const eu = new Set(terms.euCountries);

export function parcelGrams(itemGrams: number): number {
  return itemGrams + terms.packagingGrams;
}

export function shippingCents(country: string, goods: number, grams: number): number | undefined {
  const band = terms.bands.find((b) => grams <= b.upToGrams);
  if (band === undefined) return undefined;
  if (country === "DE") return goods >= toCents(terms.freeShippingFromEuros) ? 0 : toCents(band.DE);
  return toCents(eu.has(country) ? band.EU : band.WORLD);
}
