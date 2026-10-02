// Every order goes out as one DHL parcel (business contract, March 2026): rates in cents by zone and parcel
// weight (goods plus box and filling); free shipping in Germany from €49 of goods.
export type Zone = "DE" | "EU" | "WORLD";

const PACKAGING_GRAMS = 180;
const FREE_SHIPPING_FROM = 4900;
const ZONE_OF: Partial<Record<string, Zone>> = {
  DE: "DE",
  AT: "EU", BE: "EU", BG: "EU", CY: "EU", CZ: "EU", DK: "EU", EE: "EU", ES: "EU", FI: "EU",
  FR: "EU", GR: "EU", HR: "EU", HU: "EU", IE: "EU", IT: "EU", LT: "EU", LU: "EU", LV: "EU",
  MT: "EU", NL: "EU", PL: "EU", PT: "EU", RO: "EU", SE: "EU", SI: "EU", SK: "EU",
};
const PARCEL_RATES = [
  { upTo: 500, DE: 449, EU: 990, WORLD: 1590 },
  { upTo: 1000, DE: 549, EU: 1290, WORLD: 2190 },
  { upTo: 2000, DE: 649, EU: 1690, WORLD: 2990 },
  { upTo: 5000, DE: 899, EU: 2390, WORLD: 4490 },
  { upTo: 10000, DE: 1199, EU: 3490, WORLD: 6990 },
];

export function zoneOf(country: string): Zone {
  return ZONE_OF[country] ?? "WORLD";
}

export function parcelGrams(itemGrams: number): number {
  return itemGrams + PACKAGING_GRAMS;
}

export function shippingCents(country: string, goods: number, grams: number): number | undefined {
  const band = PARCEL_RATES.find((b) => grams <= b.upTo);
  if (!band) return undefined;
  const zone = zoneOf(country);
  return zone === "DE" && goods >= FREE_SHIPPING_FROM ? 0 : band[zone];
}
