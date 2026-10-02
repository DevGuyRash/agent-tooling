// DHL business contract, March 2026. Weights in grams (goods plus box and filling), amounts in cents.
const BOX_AND_FILLING_G = 180;
const FREE_DELIVERY_MIN_CENTS = 4_900;
const EU_MEMBERS: ReadonlySet<string> = new Set(
  "AT BE BG CY CZ DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split(" "),
);
const BAND_LIMITS_G = [500, 1_000, 2_000, 5_000, 10_000];
const RATES_BY_ZONE = {
  DE: [449, 549, 649, 899, 1_199],
  EU: [990, 1_290, 1_690, 2_390, 3_490],
  WORLD: [1_590, 2_190, 2_990, 4_490, 6_990],
};

export function parcelGrams(itemGrams: number): number {
  return itemGrams + BOX_AND_FILLING_G;
}

/** Shipping in cents for one parcel of `grams` with `goods` cents of goods; undefined over DHL's limit. */
export function shippingCents(country: string, goods: number, grams: number): number | undefined {
  const band = BAND_LIMITS_G.findIndex((limit) => limit >= grams);
  if (band === -1) return undefined;
  if (country === "DE") return goods < FREE_DELIVERY_MIN_CENTS ? RATES_BY_ZONE.DE[band] : 0;
  return (EU_MEMBERS.has(country) ? RATES_BY_ZONE.EU : RATES_BY_ZONE.WORLD)[band];
}
