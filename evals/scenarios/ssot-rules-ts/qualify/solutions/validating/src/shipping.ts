// Shipping terms: one DHL parcel per order. Rates from the business contract of March 2026, in cents, by
// destination zone and parcel weight (goods plus box and filling). Orders to Germany with at least €49 of
// goods ship free; we still weigh them, because DHL won't take a parcel over 10 kg.

type Band = { upTo: number; DE: number; EU: number; WORLD: number };
export type Zone = "DE" | "EU" | "WORLD";

const PACKAGING_GRAMS = 180;
const FREE_SHIPPING_FROM = 4900;
const EU_COUNTRIES: ReadonlySet<string> = new Set([
  "AT", "BE", "BG", "CY", "CZ", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
  "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
]);
const PARCEL_RATES: ReadonlyArray<Band> = [
  { upTo: 500, DE: 449, EU: 990, WORLD: 1590 },
  { upTo: 1000, DE: 549, EU: 1290, WORLD: 2190 },
  { upTo: 2000, DE: 649, EU: 1690, WORLD: 2990 },
  { upTo: 5000, DE: 899, EU: 2390, WORLD: 4490 },
  { upTo: 10000, DE: 1199, EU: 3490, WORLD: 6990 },
];
// DHL's own ceilings for a business parcel; the contract can only narrow them.
const DHL_MAX_GRAMS = 31500;
const DHL_MAX_CENTS = 20000;
const ZONES: readonly Zone[] = ["DE", "EU", "WORLD"];

// The terms are typed in by hand when the contract is renewed, so a typo should fail loudly when the shop
// starts, not quote the wrong price to a customer.
function checkTerms(): void {
  if (PACKAGING_GRAMS < 1 || PACKAGING_GRAMS > 1000) throw new Error(`packaging of ${PACKAGING_GRAMS} g is not plausible`);
  if (FREE_SHIPPING_FROM < 0) throw new Error("the free-shipping threshold is negative");
  if (EU_COUNTRIES.size < 20 || EU_COUNTRIES.size > 30) throw new Error("the EU list looks wrong");
  if (PARCEL_RATES.length < 1) throw new Error("no shipping bands");
  for (let i = 0; i < PARCEL_RATES.length; i++) {
    const band = PARCEL_RATES[i];
    if (band.upTo > DHL_MAX_GRAMS) throw new Error(`shipping band ${i} is over DHL's weight limit`);
    if (i > 0 && band.upTo <= PARCEL_RATES[i - 1].upTo) throw new Error(`shipping band ${i} is out of order`);
    for (const zone of ZONES) {
      const rate = band[zone];
      if (!Number.isInteger(rate) || rate <= 0) throw new Error(`shipping band ${i} has a bad ${zone} rate`);
      if (rate > DHL_MAX_CENTS) throw new Error(`shipping band ${i} has an implausible ${zone} rate`);
      if (i > 0 && rate < PARCEL_RATES[i - 1][zone]) throw new Error(`the ${zone} rate drops in band ${i}`);
    }
    if (band.DE > band.EU || band.EU > band.WORLD) throw new Error(`shipping band ${i}: zones out of order`);
  }
}
checkTerms();

export function zoneOf(country: string): Zone {
  if (country.length !== 2) throw new RangeError(`not a country code: ${country}`);
  return country === "DE" ? "DE" : EU_COUNTRIES.has(country) ? "EU" : "WORLD";
}

export function parcelGrams(itemGrams: number): number {
  if (!Number.isInteger(itemGrams) || itemGrams < 0) throw new RangeError(`bad weight: ${itemGrams}`);
  return itemGrams + PACKAGING_GRAMS;
}

export function shippingCents(country: string, goods: number, grams: number): number | undefined {
  if (!Number.isInteger(goods) || goods < 0) throw new RangeError(`bad goods total: ${goods}`);
  if (grams < PACKAGING_GRAMS) throw new RangeError(`a parcel of ${grams} g is lighter than its box`);
  if (grams > PARCEL_RATES[PARCEL_RATES.length - 1].upTo) return undefined;
  const band = PARCEL_RATES.find((b) => grams <= b.upTo);
  if (band === undefined) return undefined;
  const zone = zoneOf(country);
  return zone === "DE" && goods >= FREE_SHIPPING_FROM ? 0 : band[zone];
}
