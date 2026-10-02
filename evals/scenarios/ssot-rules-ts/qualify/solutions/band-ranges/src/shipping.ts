// Every order goes out as one DHL parcel. Rates from the business contract of March 2026, in cents, by
// destination zone and parcel weight (goods plus box and filling), one row per weight band. Orders to Germany
// with at least €49 of goods ship free; we still weigh them, because DHL won't take a parcel over 10 kg.
const PACKAGING_GRAMS = 180;
const FREE_SHIPPING_FROM = 4900;
const EU_COUNTRIES = new Set([
  "AT", "BE", "BG", "CY", "CZ", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
  "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
]);
const PARCEL_RATES = [
  { over: 0, upTo: 500, DE: 449, EU: 990, WORLD: 1590 },
  { over: 500, upTo: 1000, DE: 549, EU: 1290, WORLD: 2190 },
  { over: 1000, upTo: 2000, DE: 649, EU: 1690, WORLD: 2990 },
  { over: 2000, upTo: 5000, DE: 899, EU: 2390, WORLD: 4490 },
  { over: 5000, upTo: 10000, DE: 1199, EU: 3490, WORLD: 6990 },
];

export type Zone = "DE" | "EU" | "WORLD";

export function zoneOf(country: string): Zone {
  return country === "DE" ? "DE" : EU_COUNTRIES.has(country) ? "EU" : "WORLD";
}

/** The parcel's weight in grams for goods weighing itemGrams: the goods plus packaging. */
export function parcelGrams(itemGrams: number): number {
  return itemGrams + PACKAGING_GRAMS;
}

/** Shipping in cents for one parcel of `grams` with `goods` cents of goods; undefined over DHL's limit. */
export function shippingCents(country: string, goods: number, grams: number): number | undefined {
  const band = PARCEL_RATES.find((b) => grams > b.over && grams <= b.upTo);
  if (!band) return undefined;
  const zone = zoneOf(country);
  return zone === "DE" && goods >= FREE_SHIPPING_FROM ? 0 : band[zone];
}
